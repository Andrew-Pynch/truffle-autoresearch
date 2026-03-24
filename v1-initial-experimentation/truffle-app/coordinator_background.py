"""
AutoResearch Coordinator — background context submitter.

Runs on a schedule (every 10 min). Fetches status from the control server,
detects new experiments and researcher state changes, and submits context
updates with appropriate priority.
"""

import atexit
import json
import logging
import os
from datetime import datetime, timezone

from app_runtime.background import BackgroundRunContext, run_background
from config import get_machines, STATE_FILE_PATH
from data_reader import (
    get_status_sync,
    get_results_sync,
    start_researcher_sync,
    post_heartbeat_sync,
    close_sync_client,
)

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _cleanup():
    close_sync_client()
    logger.info("Background coordinator shutting down")


atexit.register(_cleanup)


def _load_state() -> dict:
    """Load state tracking last-seen experiment counts per machine."""
    if os.path.exists(STATE_FILE_PATH):
        try:
            with open(STATE_FILE_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not load state file: %s", e)
    return {}


def _save_state(state: dict) -> None:
    """Persist state to disk."""
    try:
        with open(STATE_FILE_PATH, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error("Could not save state file: %s", e)


def _format_experiment(machine_name: str, exp: dict) -> str:
    """Format an experiment into an entity-rich context string."""
    parts = [
        f"Machine: {machine_name}",
        f"Commit: {exp.get('commit', '?')}",
        f"Status: {exp.get('status', '?')}",
        f"val_bpb: {float(exp.get('val_bpb', 0)):.6f}",
        f"VRAM: {float(exp.get('memory_gb', 0)):.1f} GB",
        f"Description: {exp.get('description', '?')}",
    ]
    return " | ".join(parts)


def _determine_priority(exp: dict, global_best: float | None) -> str:
    """Determine context priority for an experiment.

    HIGH: crash, or new overall best val_bpb.
    LOW: routine keep/discard.
    """
    if exp.get("status") == "crash":
        return "high"
    bpb = exp.get("val_bpb")
    if (
        isinstance(bpb, (int, float))
        and bpb > 0
        and exp.get("status") == "keep"
        and (global_best is None or bpb < global_best)
    ):
        return "high"
    return "low"


def _ping_alive(stage: str) -> None:
    """Send a bare-minimum beacon to the control server (no auth, no deps beyond httpx)."""
    try:
        import httpx as _hx
        from config import CONTROL_SERVER_URL
        _hx.post(
            f"{CONTROL_SERVER_URL}/api/truffle/ping",
            json={"stage": stage, "ts": datetime.now(timezone.utc).isoformat()},
            timeout=10.0,
            headers={"ngrok-skip-browser-warning": "true"},
            follow_redirects=True,
        )
    except Exception as e:
        logger.error("Ping failed at stage=%s: %s", stage, e)


def run(ctx: BackgroundRunContext) -> None:
    """Main background run: detect new experiments and submit context."""
    _ping_alive("run_start")
    machines = get_machines()
    state = _load_state()
    any_updates = False

    # Get high-level status (includes researcher_running)
    status_data = get_status_sync()
    api_status = status_data.get("status", {}) if status_data.get("ok") else {}

    # Compute global best across all machines for priority decisions
    global_best = None
    all_experiments = {}
    for name in machines:
        data = get_results_sync(name)
        if data["ok"]:
            all_experiments[name] = data["experiments"]
            for exp in data["experiments"]:
                bpb = exp.get("val_bpb")
                if isinstance(bpb, (int, float)) and bpb > 0 and exp.get("status") == "keep":
                    if global_best is None or bpb < global_best:
                        global_best = bpb

    all_researchers_running = True
    actions: list[str] = []

    for name in machines:
        # Check if researcher crashed (was running last time, not running now)
        machine_status = api_status.get(name, {})
        researcher_running = machine_status.get("researcher_running", False)
        was_running = state.get(f"{name}_researcher_running", False)
        if was_running and not researcher_running:
            ctx.submit_context(
                f"RESEARCHER STOPPED on {name} — was running last check, now stopped. May have crashed.",
                priority="high",
            )
            any_updates = True
        state[f"{name}_researcher_running"] = researcher_running

        # Auto-restart stopped researchers
        if not researcher_running:
            all_researchers_running = False
            try:
                result = start_researcher_sync(name)
                if result["ok"]:
                    ctx.submit_context(f"Restarted researcher on {name}", priority="low")
                    logger.info("Restarted researcher on %s", name)
                    actions.append(f"restarted {name}")
                else:
                    logger.error("Failed to restart researcher on %s: %s", name, result.get("error"))
                    actions.append(f"restart failed on {name}: {result.get('error')}")
            except Exception as e:
                logger.error("Error restarting researcher on %s: %s", name, e)
                actions.append(f"restart error on {name}: {e}")
            any_updates = True

        if name not in all_experiments:
            ctx.submit_context(
                f"Machine {name} is unreachable — could not fetch results from control server",
                priority="low",
            )
            any_updates = True
            _save_state(state)
            continue

        experiments = all_experiments[name]
        last_count = state.get(name, 0)

        if len(experiments) <= last_count:
            _save_state(state)
            continue  # No new experiments

        new_experiments = experiments[last_count:]
        any_updates = True

        # Cap context submissions to avoid overwhelming the framework
        MAX_NEW_TO_REPORT = 5
        to_report = new_experiments[-MAX_NEW_TO_REPORT:] if len(new_experiments) > MAX_NEW_TO_REPORT else new_experiments
        if len(new_experiments) > MAX_NEW_TO_REPORT:
            ctx.submit_context(
                f"{len(new_experiments) - MAX_NEW_TO_REPORT} older experiments on {name} skipped (catching up)",
                priority="low",
            )

        try:
            for exp in to_report:
                priority = _determine_priority(exp, global_best)
                context_str = _format_experiment(name, exp)

                if priority == "high" and exp.get("status") == "crash":
                    context_str = f"CRASH DETECTED | {context_str}"
                elif priority == "high":
                    context_str = f"NEW BEST RESULT | {context_str}"

                ctx.submit_context(context_str, priority=priority)
                logger.info("Submitted %s priority context for %s/%s", priority, name, exp.get("commit", "?"))
        except Exception as e:
            logger.error("Error submitting experiment context for %s: %s", name, e)

        # Save state after each machine so we don't re-process on crash
        state[name] = len(experiments)
        _save_state(state)

    if all_researchers_running:
        ctx.submit_context("All researchers running", priority="low")
        actions.append("all running")

    if not any_updates:
        ctx.submit_context(
            "AutoResearch: no new experiments across any machines since last check.",
            priority="low",
        )

    # Post heartbeat to control server
    cycle_number = state.get("_cycle", 0) + 1
    state["_cycle"] = cycle_number
    action_summary = "; ".join(actions) if actions else "no action"
    try:
        hb_result = post_heartbeat_sync(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action_summary,
            cycle=cycle_number,
        )
        if not hb_result["ok"]:
            logger.error("Heartbeat failed: %s", hb_result.get("error"))
    except Exception as e:
        logger.error("Heartbeat error: %s", e)

    _save_state(state)
    _ping_alive("run_complete")
    logger.info("Background run complete — cycle %d, state saved", cycle_number)


if __name__ == "__main__":
    run_background(run)
