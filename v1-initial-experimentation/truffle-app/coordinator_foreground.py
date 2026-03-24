"""
AutoResearch Coordinator — MCP foreground server.

Exposes 7 tools for querying experiment status, trajectories,
cross-platform comparisons, and fleet management (start/stop/sync/logs).
"""

import atexit
import logging

from app_runtime.mcp import create_mcp_server, run_mcp_server
from config import get_machines
from data_reader import (
    get_results,
    get_status,
    get_trajectory,
    get_researcher_logs as _get_researcher_logs,
    start_researcher as _start_researcher,
    stop_researcher as _stop_researcher,
    sync_results as _sync_results,
    close_async_client,
)

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

server = create_mcp_server("AutoResearch Coordinator")
MACHINE_MAP = get_machines()


def _cleanup() -> None:
    try:
        import asyncio
        asyncio.run(close_async_client())
    except Exception:
        pass
    logger.info("Foreground server shutting down")


atexit.register(_cleanup)


def _machine_names() -> list[str]:
    return list(MACHINE_MAP.keys())


def _summarize_experiments(experiments: list[dict]) -> dict:
    """Compute aggregate stats from a list of experiments."""
    if not experiments:
        return {
            "count": 0,
            "best_val_bpb": None,
            "keeps": 0,
            "discards": 0,
            "crashes": 0,
            "last": None,
        }
    keeps = [e for e in experiments if e.get("status") == "keep"]
    discards = [e for e in experiments if e.get("status") == "discard"]
    crashes = [e for e in experiments if e.get("status") == "crash"]
    valid = [e for e in experiments if isinstance(e.get("val_bpb"), (int, float)) and e["val_bpb"] > 0]
    best = min(valid, key=lambda e: e["val_bpb"]) if valid else None
    return {
        "count": len(experiments),
        "best_val_bpb": best["val_bpb"] if best else None,
        "best_commit": best.get("commit") if best else None,
        "keeps": len(keeps),
        "discards": len(discards),
        "crashes": len(crashes),
        "last": experiments[-1],
    }


@server.tool(
    "get_experiment_status",
    description=(
        "Get current experiment status for one or all machines. "
        "Parameters: machine (str, default 'all', or specific machine name: 4090, 3080). "
        "Returns: JSON with per-machine experiment counts, best val_bpb, "
        "and whether the researcher is currently running."
    ),
)
async def get_experiment_status(machine: str = "all") -> dict:
    if machine != "all" and machine not in MACHINE_MAP:
        return {
            "status": "error",
            "error": f"Unknown machine '{machine}'",
            "available_machines": _machine_names(),
        }

    data = await get_status()
    if not data["ok"]:
        return {"status": "error", "error": data["error"]}

    api_status = data["status"]
    results = {}

    targets = _machine_names() if machine == "all" else [machine]
    for name in targets:
        if name in api_status:
            info = api_status[name]
            if "error" in info:
                results[name] = {"status": "error", "error": info["error"]}
            else:
                results[name] = {
                    "status": "ok",
                    "experiment_count": info.get("experiment_count", 0),
                    "best_val_bpb": info.get("best_val_bpb"),
                    "researcher_running": info.get("researcher_running", False),
                }
        else:
            results[name] = {"status": "error", "error": f"No data for {name}"}

    return {"status": "ok", "machines": results}


@server.tool(
    "get_optimization_trajectory",
    description=(
        "Get the full chronological experiment list for a machine. "
        "Parameters: machine (str, required, one of: 4090, 3080). "
        "Returns: JSON with chronological trajectory where each experiment is annotated "
        "with is_new_best (whether it set a new lowest val_bpb at the time it ran)."
    ),
)
async def get_optimization_trajectory(machine: str) -> dict:
    if machine not in MACHINE_MAP:
        return {
            "status": "error",
            "error": f"Unknown machine '{machine}'",
            "available_machines": _machine_names(),
        }

    data = await get_trajectory(machine)
    if not data["ok"]:
        return {"status": "error", "error": data["error"]}

    experiments = data["trajectory"]
    best_so_far = float("inf")
    annotated = []
    for exp in experiments:
        is_new_best = False
        bpb = exp.get("val_bpb")
        if isinstance(bpb, (int, float)) and bpb > 0 and bpb < best_so_far:
            best_so_far = bpb
            is_new_best = True
        annotated.append({**exp, "is_new_best": is_new_best})

    return {"status": "ok", "machine": machine, "trajectory": annotated}


@server.tool(
    "compare_platforms",
    description=(
        "Compare experiment results across all platforms side-by-side. "
        "Parameters: none. "
        "Returns: JSON with per-machine summaries and identifies the leader "
        "(machine with the lowest val_bpb)."
    ),
)
async def compare_platforms() -> dict:
    comparisons = {}
    best_overall = None
    leader = None

    for name in MACHINE_MAP:
        data = await get_results(name)
        if not data["ok"]:
            comparisons[name] = {"status": "error", "error": data["error"]}
            continue
        summary = _summarize_experiments(data["experiments"])
        comparisons[name] = {"status": "ok", **summary}
        if summary["best_val_bpb"] is not None:
            if best_overall is None or summary["best_val_bpb"] < best_overall:
                best_overall = summary["best_val_bpb"]
                leader = name

    return {
        "status": "ok",
        "platforms": comparisons,
        "leader": leader,
        "best_val_bpb": best_overall,
    }


@server.tool(
    "start_researcher",
    description=(
        "Start the autonomous research loop on a machine. "
        "Parameters: machine (str, required, one of: 4090, 3080). "
        "Returns: JSON with status and session name, or error if already running."
    ),
)
async def start_researcher_tool(machine: str) -> dict:
    if machine not in MACHINE_MAP:
        return {
            "status": "error",
            "error": f"Unknown machine '{machine}'",
            "available_machines": _machine_names(),
        }
    data = await _start_researcher(machine)
    if not data["ok"]:
        return {"status": "error", "error": data["error"]}
    return {"status": "ok", "machine": machine, **data}


@server.tool(
    "stop_researcher",
    description=(
        "Stop the autonomous research loop on a machine. "
        "Parameters: machine (str, required, one of: 4090, 3080). "
        "Returns: JSON with status, or error if no researcher is running."
    ),
)
async def stop_researcher_tool(machine: str) -> dict:
    if machine not in MACHINE_MAP:
        return {
            "status": "error",
            "error": f"Unknown machine '{machine}'",
            "available_machines": _machine_names(),
        }
    data = await _stop_researcher(machine)
    if not data["ok"]:
        return {"status": "error", "error": data["error"]}
    return {"status": "ok", "machine": machine, **data}


@server.tool(
    "sync_results",
    description=(
        "Trigger result sync to GitHub for a machine. "
        "Parameters: machine (str, required, one of: 4090, 3080). "
        "Returns: JSON with sync output."
    ),
)
async def sync_results_tool(machine: str) -> dict:
    if machine not in MACHINE_MAP:
        return {
            "status": "error",
            "error": f"Unknown machine '{machine}'",
            "available_machines": _machine_names(),
        }
    data = await _sync_results(machine)
    if not data["ok"]:
        return {"status": "error", "error": data["error"]}
    return {"status": "ok", "machine": machine, **data}


@server.tool(
    "get_researcher_logs",
    description=(
        "Get recent log output from the autonomous researcher on a machine. "
        "Parameters: machine (str, required, one of: 4090, 3080). "
        "Returns: JSON with recent log lines showing what the researcher is doing."
    ),
)
async def get_researcher_logs_tool(machine: str) -> dict:
    if machine not in MACHINE_MAP:
        return {
            "status": "error",
            "error": f"Unknown machine '{machine}'",
            "available_machines": _machine_names(),
        }
    data = await _get_researcher_logs(machine)
    if not data["ok"]:
        return {"status": "error", "error": data["error"]}
    return {"status": "ok", "machine": machine, "lines": data["lines"], "log_file": data.get("log_file")}


def main() -> None:
    run_mcp_server(server, logger)


if __name__ == "__main__":
    main()
