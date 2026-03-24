"""
AutoResearch Control Server

FastAPI server for coordinating ML experiments across machines.
Runs on big-bertha (3080), controls big-ron (4090) via SSH.
Serves the React dashboard as static files.
"""

import csv
import io
import os
import pathlib
import subprocess
import time

import paramiko
from fastapi import Depends, FastAPI, HTTPException, Header
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="AutoResearch Control Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Machine config -- add H200 here later
# ---------------------------------------------------------------------------
MACHINES: dict[str, dict] = {
    "3080": {"host": "localhost", "type": "local"},
    "4090": {"host": os.environ.get("SSH_HOST_4090", ""), "user": os.environ.get("SSH_USER_4090", ""), "type": "ssh"},
}

RESULTS_PATH = "~/personal/truffle-autoresearch/autoresearch/results.tsv"
AUTORESEARCH_DIR = "~/personal/truffle-autoresearch/autoresearch"
REPO_ROOT = "~/personal/truffle-autoresearch"
TRAIN_CMD = "cd ~/personal/truffle-autoresearch/autoresearch && uv run train.py"
LOG_PATH = "~/personal/truffle-autoresearch/autoresearch/run.log"
TRUFFLE_APP_PATH = "~/personal/truffle-autoresearch/truffle-app/"

API_TOKEN = os.environ.get("CONTROL_API_TOKEN", "")

_heartbeats: list[dict] = []
_MAX_HEARTBEATS = 50

TMUX_SESSION = "truffle-autoresearch"
TMUX_WINDOW = "0"
TMUX_TARGET = f"{TMUX_SESSION}:{TMUX_WINDOW}"
PROMPT_FILE = "/tmp/researcher-prompt.txt"

RESEARCHER_PROMPT = """\
You are an autonomous autoresearch agent. Your job is to improve a small language model's val_bpb score by modifying train.py hyperparameters.

CRITICAL INSTRUCTIONS:
1. Read program.md for the full autoresearch protocol
2. Read results.tsv to see what has already been tried — DO NOT repeat failed experiments
3. Read train.py to see the current state (it reflects the best configuration so far)
4. Pick a NEW hyperparameter modification that hasn't been tried
5. Edit train.py with your change
6. Run: uv run train.py
7. Wait for training to complete (~5 minutes)
8. Check run.log for the final val_bpb score
9. Record the result in results.tsv following the exact format in program.md
10. If val_bpb IMPROVED: keep the change (git add, git commit with descriptive message)
11. If val_bpb DID NOT IMPROVE: revert train.py to previous state (git checkout train.py)
12. Repeat from step 4 — do as many experiments as you can

STRATEGY GUIDANCE:
- Every 'make it bigger' attempt has failed because fewer training steps fit in 5 minutes
- Focus on subtle hyperparameter tuning: learning rates, warmdown ratios, weight decay, etc.
- Check results.tsv carefully — many obvious things have been tried already
- The current best configs were found through LR tuning, not architecture changes
- Think creatively: curriculum learning, loss function tweaks, initialization schemes, etc.

DO NOT modify prepare.py or the evaluation infrastructure.
DO NOT delete or corrupt results.tsv.
ALWAYS use 'uv run train.py' to run training (not python train.py).
ALWAYS wait for training to fully complete before checking results."""

RESEARCHER_SCRIPT = f"""\
#!/bin/bash
unset ANTHROPIC_API_KEY
cd {AUTORESEARCH_DIR}
PROMPT=$(cat {PROMPT_FILE})
exec claude -p --dangerously-skip-permissions --model opus "$PROMPT"
"""

RESEARCHER_SCRIPT_PATH = "/tmp/run-researcher.sh"

TRUFFILE_COMMANDS = {
    "scan": "truffile scan",
    "list-apps": "truffile list apps",
    "list-devices": "truffile list devices",
    "validate": f"truffile validate {TRUFFLE_APP_PATH}",
    "deploy": f"truffile deploy {TRUFFLE_APP_PATH}",
    "connect": "truffile connect",
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def verify_token(authorization: str = Header(None)):
    if not API_TOKEN:
        return  # no token configured = no auth (dev mode)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if authorization[7:] != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


# ---------------------------------------------------------------------------
# SSH helper
# ---------------------------------------------------------------------------
def _ssh_client(machine: dict) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=machine["host"],
        username=machine["user"],
        key_filename=os.path.expanduser("~/.ssh/id_ed25519"),
        timeout=10,
    )
    return client


def _ssh_exec(machine: dict, cmd: str) -> tuple[str, str, int]:
    """Run a command via SSH. Returns (stdout, stderr, exit_code)."""
    client = _ssh_client(machine)
    try:
        _, stdout, stderr = client.exec_command(cmd, timeout=30)
        exit_code = stdout.channel.recv_exit_status()
        return stdout.read().decode(), stderr.read().decode(), exit_code
    finally:
        client.close()


def _local_exec(cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    """Run a command locally. Returns (stdout, stderr, exit_code)."""
    r = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout,
    )
    return r.stdout, r.stderr, r.returncode


def _exec(machine_id: str, cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    """Run a command on the target machine."""
    m = MACHINES[machine_id]
    if m["type"] == "local":
        return _local_exec(cmd, timeout=timeout)
    return _ssh_exec(m, cmd)


def _get_machine(machine_id: str) -> dict:
    if machine_id not in MACHINES:
        raise HTTPException(status_code=404, detail=f"Unknown machine: {machine_id}")
    return MACHINES[machine_id]


# ---------------------------------------------------------------------------
# Results parsing
# ---------------------------------------------------------------------------
def _parse_results(raw: str) -> list[dict]:
    rows = []
    reader = csv.DictReader(io.StringIO(raw), delimiter="\t")
    for row in reader:
        try:
            row["val_bpb"] = float(row["val_bpb"])
        except (ValueError, TypeError):
            pass
        try:
            row["memory_gb"] = float(row["memory_gb"])
        except (ValueError, TypeError):
            pass
        rows.append(row)
    return rows


def _read_results(machine_id: str) -> list[dict]:
    """Read and parse results.tsv from a machine."""
    _get_machine(machine_id)
    stdout, stderr, code = _exec(machine_id, f"cat {RESULTS_PATH}")
    if code != 0:
        raise HTTPException(status_code=500, detail=f"Failed to read results: {stderr}")
    return _parse_results(stdout)


def _write_prompt_file(machine_id: str) -> None:
    """Write the researcher prompt to /tmp on the target machine."""
    m = MACHINES[machine_id]
    if m["type"] == "local":
        pathlib.Path(PROMPT_FILE).write_text(RESEARCHER_PROMPT)
    else:
        # Heredoc with quoted delimiter prevents shell expansion
        cmd = f"cat > {PROMPT_FILE} << 'RESEARCHER_PROMPT_EOF'\n{RESEARCHER_PROMPT}\nRESEARCHER_PROMPT_EOF"
        _ssh_exec(m, cmd)


def _write_researcher_script(machine_id: str) -> None:
    """Write the researcher wrapper script to /tmp on the target machine."""
    m = MACHINES[machine_id]
    if m["type"] == "local":
        p = pathlib.Path(RESEARCHER_SCRIPT_PATH)
        p.write_text(RESEARCHER_SCRIPT)
        p.chmod(0o755)
    else:
        cmd = f"cat > {RESEARCHER_SCRIPT_PATH} << 'SCRIPT_EOF'\n{RESEARCHER_SCRIPT}\nSCRIPT_EOF"
        _ssh_exec(m, cmd)
        _ssh_exec(m, f"chmod +x {RESEARCHER_SCRIPT_PATH}")


def _researcher_running(machine_id: str) -> bool:
    """Check if a claude researcher process is actually running."""
    _get_machine(machine_id)
    cmd = "pgrep -f '[c]laude -p --dangerously-skip-permissions' > /dev/null 2>&1"
    _, _, code = _exec(machine_id, cmd)
    return code == 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/status", dependencies=[Depends(verify_token)])
def status():
    result = {}
    for machine_id in MACHINES:
        try:
            experiments = _read_results(machine_id)
            keep = [e for e in experiments if e.get("status") == "keep"]
            best_bpb = min((e["val_bpb"] for e in keep if isinstance(e.get("val_bpb"), float)), default=None)
            result[machine_id] = {
                "experiment_count": len(experiments),
                "best_val_bpb": best_bpb,
                "researcher_running": _researcher_running(machine_id),
            }
        except Exception as e:
            result[machine_id] = {"error": str(e)}
    return result


@app.get("/api/results/{machine}", dependencies=[Depends(verify_token)])
def results(machine: str):
    _get_machine(machine)
    return {"machine": machine, "results": _read_results(machine)}


@app.get("/api/results/{machine}/trajectory", dependencies=[Depends(verify_token)])
def trajectory(machine: str):
    _get_machine(machine)
    rows = _read_results(machine)
    for i, row in enumerate(rows, 1):
        row["experiment_num"] = i
    return rows


@app.get("/api/logs/{machine}", dependencies=[Depends(verify_token)])
def logs(machine: str):
    _get_machine(machine)
    cmd = f"tail -100 {LOG_PATH}"
    stdout, stderr, code = _exec(machine, cmd)
    if code != 0:
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {stderr}")
    lines = stdout.splitlines()
    return {"lines": lines, "machine": machine}


@app.post("/api/truffile/{command}", dependencies=[Depends(verify_token)])
def truffile(command: str):
    if command not in TRUFFILE_COMMANDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown command: {command}. Allowed: {', '.join(TRUFFILE_COMMANDS)}",
        )
    cmd = TRUFFILE_COMMANDS[command]
    # truffile is installed locally on big-bertha (3080)
    stdout, stderr, exit_code = _local_exec(cmd, timeout=60)
    return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}


@app.post("/api/researcher/{machine}/start", dependencies=[Depends(verify_token)])
def researcher_start(machine: str):
    _get_machine(machine)

    if _researcher_running(machine):
        raise HTTPException(status_code=409, detail=f"Researcher already running on {machine}")

    # Clean up stale window from previous run
    _exec(machine, f"tmux kill-window -t {TMUX_TARGET} 2>/dev/null || true")

    # Write prompt file and wrapper script to target machine
    _write_prompt_file(machine)
    _write_researcher_script(machine)

    # Create window 0 if it doesn't exist, then run the wrapper script
    create_win = f"tmux new-window -t {TMUX_SESSION}:{TMUX_WINDOW} 2>/dev/null || true"
    send_cmd = f"tmux send-keys -t {TMUX_TARGET} 'bash {RESEARCHER_SCRIPT_PATH}' Enter"
    cmd = f"{create_win} && {send_cmd}"

    _, stderr, code = _exec(machine, cmd)
    if code != 0:
        raise HTTPException(status_code=500, detail=f"Failed to start researcher: {stderr}")

    return {"status": "started", "machine": machine, "session": TMUX_TARGET}


@app.post("/api/researcher/{machine}/stop", dependencies=[Depends(verify_token)])
def researcher_stop(machine: str):
    _get_machine(machine)

    if not _researcher_running(machine):
        raise HTTPException(status_code=404, detail=f"No researcher running on {machine}")

    # Send Ctrl+C
    _exec(machine, f"tmux send-keys -t {TMUX_TARGET} C-c")

    # Poll up to 5s for process to die
    for _ in range(10):
        time.sleep(0.5)
        if not _researcher_running(machine):
            break
    else:
        # Force-kill if Ctrl+C didn't work
        _exec(machine, "pkill -9 -f 'claude -p --dangerously-skip-permissions'")
        time.sleep(0.5)

    # Clean up tmux window
    _exec(machine, f"tmux kill-window -t {TMUX_TARGET} 2>/dev/null || true")

    return {"status": "stopped", "machine": machine, "session": TMUX_TARGET}


@app.get("/api/researcher/{machine}/logs", dependencies=[Depends(verify_token)])
def researcher_logs(machine: str):
    _get_machine(machine)
    cmd = f"tmux capture-pane -t {TMUX_TARGET} -p | tail -50"
    stdout, _, code = _exec(machine, cmd)
    if code != 0:
        return {"lines": [], "machine": machine}
    return {"lines": stdout.splitlines(), "machine": machine}


@app.post("/api/sync/{machine}", dependencies=[Depends(verify_token)])
def sync(machine: str):
    _get_machine(machine)
    cmd = f"cd {REPO_ROOT} && ./sync_results.sh {machine}"
    stdout, stderr, code = _exec(machine, cmd, timeout=60)
    if code != 0:
        raise HTTPException(status_code=500, detail=f"Sync failed: {stderr}")
    return {"status": "synced", "machine": machine, "output": stdout.strip()}


# ---------------------------------------------------------------------------
# Truffle heartbeat
# ---------------------------------------------------------------------------
class HeartbeatPayload(BaseModel):
    timestamp: str
    action: str
    cycle: int


@app.post("/api/truffle/heartbeat", dependencies=[Depends(verify_token)])
def truffle_heartbeat(payload: HeartbeatPayload):
    _heartbeats.append(payload.model_dump())
    while len(_heartbeats) > _MAX_HEARTBEATS:
        _heartbeats.pop(0)
    return {"ok": True}


@app.get("/api/truffle/heartbeat", dependencies=[Depends(verify_token)])
def truffle_heartbeat_history():
    return {"heartbeats": _heartbeats}


# ---------------------------------------------------------------------------
# Debug ping — bare-minimum "I'm alive" beacon from background app
# ---------------------------------------------------------------------------
_pings: list[dict] = []
_MAX_PINGS = 100


@app.post("/api/truffle/ping")
def truffle_ping(payload: dict = None):
    """No-auth endpoint so the BG app can ping even if auth is misconfigured."""
    import datetime
    entry = {
        "received_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "payload": payload or {},
    }
    _pings.append(entry)
    while len(_pings) > _MAX_PINGS:
        _pings.pop(0)
    return {"ok": True}


@app.get("/api/truffle/ping")
def truffle_ping_history():
    return {"pings": _pings}


# ---------------------------------------------------------------------------
# Serve React dashboard (must be after all API routes)
# ---------------------------------------------------------------------------
_dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard", "dist")
if os.path.isdir(_dashboard_dir):
    app.mount("/", StaticFiles(directory=_dashboard_dir, html=True), name="dashboard")
