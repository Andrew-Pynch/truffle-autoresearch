"""FastAPI control server for coordinating experiments across the fleet.

Reads fleet.yaml to discover machines, uses target.yaml for metric info,
and routes all machine interaction through MachineExecutor.
"""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from truffle_autoresearch.config.fleet import ConfigError, FleetConfig, load_fleet_config
from truffle_autoresearch.config.target import TargetConfig
from truffle_autoresearch.fleet.ssh import SSHError
from truffle_autoresearch.server.executor import ExecutorError, MachineExecutor
from truffle_autoresearch.server.results import annotate_trajectory, parse_results_tsv
from truffle_autoresearch.targets.loader import find_targets, get_target

logger = logging.getLogger(__name__)

TMUX_SESSION = "autoresearch"


# ---------------------------------------------------------------------------
# Server state — initialised during lifespan
# ---------------------------------------------------------------------------
class _ServerState:
    fleet: FleetConfig
    executor: MachineExecutor
    base_dir: Path
    api_token: str


_state: _ServerState | None = None


def _save_server_state(port: int, token: str) -> None:
    """Persist server PID, port, and token so CLI commands can reach us."""
    import json
    from truffle_autoresearch.config.paths import SERVER_STATE_PATH

    SERVER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SERVER_STATE_PATH.write_text(
        json.dumps({"pid": os.getpid(), "port": port, "token": token})
    )


def _clear_server_state() -> None:
    from truffle_autoresearch.config.paths import SERVER_STATE_PATH

    SERVER_STATE_PATH.unlink(missing_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _state
    _state = _ServerState()
    _state.fleet = load_fleet_config()
    _state.base_dir = Path.cwd()
    _state.api_token = os.environ.get("AUTORESEARCH_API_TOKEN", "")
    if not _state.api_token:
        _state.api_token = secrets.token_urlsafe(32)
        # Print so the user can copy it
        print(f"\n  Generated API token: {_state.api_token}\n")
    _state.executor = MachineExecutor(_state.fleet)
    _save_server_state(_state.fleet.host.port, _state.api_token)
    logger.info("Control server ready — %d machine(s) in fleet", len(_state.fleet.machines))
    yield
    _state.executor.close()
    _clear_server_state()
    _state = None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="AutoResearch Control Server", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(SSHError)
async def ssh_error_handler(request, exc):
    return JSONResponse(status_code=502, content={"detail": f"SSH error: {exc}"})


@app.exception_handler(ExecutorError)
async def executor_error_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def verify_token(authorization: str = Header(None)) -> None:
    if _state is None:
        raise HTTPException(status_code=503, detail="Server not initialised")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if authorization[7:] != _state.api_token:
        raise HTTPException(status_code=403, detail="Invalid token")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_target(target: str | None) -> tuple[Path, TargetConfig]:
    """Resolve a target name to (directory, config).

    If target is None, auto-detect when exactly one target exists in CWD.
    """
    if target is not None:
        try:
            return get_target(target)
        except ConfigError:
            raise HTTPException(status_code=404, detail=f"Target not found: {target}")
    targets = find_targets()
    if len(targets) == 0:
        raise HTTPException(status_code=400, detail="No targets found in working directory")
    if len(targets) > 1:
        names = [cfg.name for _, cfg in targets]
        raise HTTPException(
            status_code=400,
            detail=f"Multiple targets found: {names}. Specify ?target=<name>",
        )
    return targets[0]


def _validate_machine(machine_name: str) -> None:
    names = {m.name for m in _state.fleet.machines}
    if machine_name not in names:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown machine: {machine_name}. Available: {sorted(names)}",
        )


def _results_path(target_cfg: TargetConfig) -> str:
    """Absolute path to results.tsv for a target (same path on all machines)."""
    return str(_state.base_dir / target_cfg.name / "results.tsv")


def _log_path(target_cfg: TargetConfig) -> str:
    """Absolute path to the metric source log for a target."""
    return str(_state.base_dir / target_cfg.name / target_cfg.metric.source)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ResearcherStartRequest(BaseModel):
    target: str = "toy-lm"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/status", dependencies=[Depends(verify_token)])
def status(target: str | None = Query(None)) -> dict[str, Any]:
    _target_dir, target_cfg = _resolve_target(target)
    metric_name = target_cfg.metric.name
    direction = target_cfg.metric.direction

    machines: dict[str, Any] = {}
    for machine in _state.fleet.machines:
        try:
            out, _err, code = _state.executor.execute(
                machine.name, f"cat {_results_path(target_cfg)}"
            )
            if code != 0:
                # No results file yet — that's fine
                rows: list[dict] = []
            else:
                rows = parse_results_tsv(out)

            keep = [r for r in rows if r.get("status") == "keep"]
            metric_values = [
                r[metric_name]
                for r in keep
                if isinstance(r.get(metric_name), float)
            ]
            if metric_values:
                best = min(metric_values) if direction == "minimize" else max(metric_values)
            else:
                best = None

            researcher_running = _state.executor.tmux_running(machine.name, TMUX_SESSION)

            machines[machine.name] = {
                "experiment_count": len(rows),
                "best_metric": best,
                "researcher_running": researcher_running,
            }
        except Exception as e:
            machines[machine.name] = {"error": str(e)}

    return {"machines": machines}


@app.get("/api/results/{machine}", dependencies=[Depends(verify_token)])
def results(machine: str, target: str | None = Query(None)) -> dict[str, Any]:
    _validate_machine(machine)
    _target_dir, target_cfg = _resolve_target(target)
    out, err, code = _state.executor.execute(machine, f"cat {_results_path(target_cfg)}")
    if code != 0:
        return {"results": []}
    return {"results": parse_results_tsv(out)}


@app.get("/api/results/{machine}/trajectory", dependencies=[Depends(verify_token)])
def trajectory(machine: str, target: str | None = Query(None)) -> dict[str, Any]:
    _validate_machine(machine)
    _target_dir, target_cfg = _resolve_target(target)
    out, err, code = _state.executor.execute(machine, f"cat {_results_path(target_cfg)}")
    if code != 0:
        return {"trajectory": []}
    rows = parse_results_tsv(out)
    return {
        "trajectory": annotate_trajectory(
            rows, target_cfg.metric.name, target_cfg.metric.direction
        )
    }


@app.get("/api/logs/{machine}", dependencies=[Depends(verify_token)])
def logs(machine: str, target: str | None = Query(None)) -> dict[str, Any]:
    _validate_machine(machine)
    _target_dir, target_cfg = _resolve_target(target)
    out, err, code = _state.executor.execute(
        machine, f"tail -100 {_log_path(target_cfg)}"
    )
    if code != 0:
        return {"lines": []}
    return {"lines": out.splitlines()}


@app.post("/api/researcher/{machine}/start", dependencies=[Depends(verify_token)])
def researcher_start(machine: str, body: ResearcherStartRequest) -> dict[str, Any]:
    _validate_machine(machine)

    if _state.executor.tmux_running(machine, TMUX_SESSION):
        raise HTTPException(status_code=409, detail=f"Researcher already running on {machine}")

    # Launch the autoresearch loop for this target on the given machine
    import sys

    target_dir = _state.base_dir / body.target
    cmd = (
        f"{sys.executable} -m truffle_autoresearch.loop"
        f" --target-dir {target_dir}"
        f" --machine {machine}"
    )
    _state.executor.tmux_start(machine, TMUX_SESSION, cmd)

    return {"status": "started", "machine": machine, "target": body.target}


@app.post("/api/researcher/{machine}/stop", dependencies=[Depends(verify_token)])
def researcher_stop(machine: str) -> dict[str, Any]:
    _validate_machine(machine)

    if not _state.executor.tmux_running(machine, TMUX_SESSION):
        raise HTTPException(status_code=404, detail=f"No researcher running on {machine}")

    _state.executor.tmux_kill(machine, TMUX_SESSION)
    return {"status": "stopped", "machine": machine}


@app.post("/api/sync/{machine}", dependencies=[Depends(verify_token)])
def sync(machine: str) -> dict[str, Any]:
    _validate_machine(machine)
    cmd = f"cd {_state.base_dir} && ./sync_results.sh"
    out, err, code = _state.executor.execute(machine, cmd, timeout=60)
    if code != 0:
        raise HTTPException(status_code=500, detail=f"Sync failed: {err}")
    return {"status": "synced", "machine": machine, "output": out.strip()}


@app.get("/api/researcher/{machine}/logs", dependencies=[Depends(verify_token)])
def researcher_logs(machine: str) -> dict[str, Any]:
    _validate_machine(machine)
    # Find the latest autoresearch agent log
    latest_out, _err, code = _state.executor.execute(
        machine, "ls -t /tmp/autoresearch-*.log 2>/dev/null | head -1"
    )
    if code != 0 or not latest_out.strip():
        return {"lines": [], "machine": machine}
    latest_log = latest_out.strip()
    out, _err, code = _state.executor.execute(machine, f"tail -50 {latest_log}")
    if code != 0:
        return {"lines": [], "machine": machine}
    return {"lines": out.splitlines(), "machine": machine}
