# Control Server

FastAPI server for coordinating autoresearch experiments across GPU machines and serving the fleet dashboard.

Runs on **big-bertha** (RTX 3080), controls **big-ron** (RTX 4090) via SSH.

## Setup

```bash
pip install -r requirements.txt
```

Requirements: `fastapi`, `uvicorn`, `paramiko`

## Running

```bash
CONTROL_API_TOKEN=<your-token> SSH_HOST_4090=<ip> SSH_USER_4090=<user> ./run.sh
```

The server starts on port **8420** and serves both the API and the built React dashboard.

- API: `http://localhost:8420/api/`
- Dashboard: `http://localhost:8420/`

If the dashboard hasn't been built yet (`../dashboard/dist/` doesn't exist), only the API is available.

## Authentication

All endpoints except `/api/health` require a Bearer token in the `Authorization` header.

Set via the `CONTROL_API_TOKEN` environment variable. If unset, auth is disabled (dev mode).

```bash
curl -H "Authorization: Bearer $CONTROL_API_TOKEN" http://localhost:8420/api/status
```

## Machine Configuration

Two machines are configured in `MACHINES`:

| ID     | Host          | Type  | GPU       |
|--------|---------------|-------|-----------|
| `3080` | localhost     | local | RTX 3080  |
| `4090` | `$SSH_HOST_4090` | ssh   | RTX 4090  |

SSH connections use `~/.ssh/id_ed25519` with user `$SSH_USER_4090`.

## API Endpoints

### Health & Status

- **GET `/api/health`** - Health check (no auth required)
- **GET `/api/status`** - Per-machine status: experiment count, best val_bpb, researcher running state

### Results

- **GET `/api/results/{machine}`** - Full parsed results.tsv for a machine
- **GET `/api/results/{machine}/trajectory`** - Results with `experiment_num` added (1-indexed), for charting optimization trajectory. Includes all experiments (keep, discard, crash).

### Researcher Control

- **POST `/api/researcher/{machine}/start`** - Start a researcher tmux session (`researcher-{machine}`) running `train.py`
- **POST `/api/researcher/{machine}/stop`** - Kill the researcher tmux session

### Sync

- **POST `/api/sync/{machine}`** - Run `sync_results.sh` to copy results.tsv into `results/{machine}-results.tsv` and git push

### Logs

- **GET `/api/logs/{machine}`** - Last 100 lines of `autoresearch/run.log` from the specified machine. Returns `{"lines": [...], "machine": "..."}`

### Truffle Operations

- **POST `/api/truffile/{command}`** - Execute a whitelisted truffile command on big-ron (4090) via SSH. Returns `{"stdout": "...", "stderr": "...", "exit_code": 0}`

Allowed commands:

| Command      | Executes                                              |
|--------------|-------------------------------------------------------|
| `scan`       | `truffile scan`                                       |
| `list-apps`  | `truffile list-apps`                                  |
| `validate`   | `truffile validate ~/personal/truffle-autoresearch/truffle-app/` |
| `deploy`     | `truffile deploy ~/personal/truffle-autoresearch/truffle-app/`   |
| `connect`    | `truffile connect`                                    |

Any other command returns 400. No arbitrary command execution is allowed.

## Results TSV Format

Tab-separated with columns:

```
commit	val_bpb	memory_gb	status	description
```

- `commit` - Short git hash
- `val_bpb` - Validation bits per byte (lower is better)
- `memory_gb` - Peak VRAM usage
- `status` - `keep`, `discard`, or `crash`
- `description` - What was changed in this experiment
