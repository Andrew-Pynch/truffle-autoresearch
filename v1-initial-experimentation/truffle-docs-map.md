# Truffle Computer -- SDK Documentation Map

> Comprehensive reference derived from [deepshard/truffile](https://github.com/deepshard/truffile). Use this document as complete context for building, deploying, and reasoning about Truffle apps.

---

## 1. Overview

**Truffile** is the Python SDK/CLI for Truffle devices. It discovers, connects to, validates, deploys, and manages apps on your Truffle, plus talks to on-device inference directly.

| Fact | Value |
|------|-------|
| Package | `pip install truffile` |
| Python | 3.12+ |
| Prerequisites | Truffle device + Symphony desktop client |
| Transport | gRPC (device control) + HTTP/SSE (build containers) |
| Proto source | `truffle/` (vendored, sync via `scripts/sync_protos.sh`) |
| Config file | `truffile.yaml` per app |
| Local state | `~/.local/share/truffile/state.json` (platformdirs) |

### Architecture

The SDK has two transport layers:

1. **gRPC channel to TruffleOS** -- used for device auth, session registration, app queries, build session lifecycle (start/finish/discard), and app deletion.
2. **HTTP/SSE to container endpoints** -- used during build sessions for file upload, command execution (streamed via SSE), and interactive terminal (WebSocket at `/term`).

The CLI (`cli.py`, ~92K) orchestrates both layers and provides the user-facing REPL, deploy flow, scanning (mDNS), and inference chat.

---

## 2. App Model

Truffle apps are **containerized programs** that run on your Truffle and extend what the on-device agent can do.

### App Types

| Type | Internal Name | When It Runs | What It Does |
|------|--------------|--------------|--------------|
| **Foreground** | `focus` | On demand | Exposes MCP tools (served over `streamable-http`) the agent can call during tasks |
| **Background** | `ambient` | On schedule | Submits context to the proactive agent via `ctx.bg.submit_context()` |
| **Hybrid** | `hybrid` | On demand + schedule | Single app package provides MCP tools AND scheduled context emission |

### Runtime Imports

- **Foreground**: `from app_runtime.mcp import create_mcp_server, run_mcp_server`
- **Background**: `from app_runtime.background import BackgroundRunContext, run_background`

### Mental Model

- **FG path = tool-serving**: the app process is a callable capability surface (MCP spec).
- **BG path = context/proactivity**: scheduled runs feed the proactive agent with fresh signals.
- Proactivity can take actions AND persist memory based on BG outputs.
- BG context from one app can trigger actions in another app (e.g., Instagram message about an Amazon order -> add item to cart).

### When to use which:

- Use `fg` when you need direct tool invocation from tasks.
- Use `bg` when you need periodic monitoring, summaries, or event-driven context.
- Use `both` when the same app should both expose tools and continuously feed proactivity/memory.

---

## 3. truffile.yaml Schema

The `truffile.yaml` file is the single source of truth for app configuration. It defines metadata, process configs, build steps, and scheduling.

### metadata (required)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | YES | App display name |
| `bundle_id` | string | no | Reverse-DNS identifier (e.g. `org.deepshard.kalshi`). Auto-derived from name if missing. |
| `description` | string | no | App description text |
| `icon_file` | string | no | Path to icon PNG (deploy requires an icon) |
| `type` | string | no | Legacy: `foreground`/`focus` or `background`/`ambient`. Overridden by explicit fg/bg blocks. |

### metadata.foreground (optional)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `process.cmd` | list[str] | YES | Command to run (e.g. `["python", "app_fg.py"]`) |
| `process.working_directory` | string | no | Working dir inside container (default: `/`). Alias: `cwd` |
| `process.environment` | map[str,str] | no | Env vars. Keys must match `[A-Za-z_][A-Za-z0-9_]*`. Alias: `env` |

### metadata.background (optional)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `process.cmd` | list[str] | YES | Command to run for BG process |
| `process.working_directory` | string | no | Working dir inside container |
| `process.environment` | map[str,str] | no | Env vars for BG process |
| `default_schedule` | object | YES | Required for BG apps. See Scheduling section. |

### steps (list, optional)

| Step Type | Fields | Notes |
|-----------|--------|-------|
| `type: bash` | `name`, `run` | Shell script executed in build container |
| `type: files` | `name`, `files[]` | Each file entry has `source` (local) + `destination` (container). Python files get syntax-checked at validation time. |

### Top-level legacy fields

| Field | Type | Notes |
|-------|------|-------|
| `files` | list | Legacy file copy steps (same as `steps[type=files].files`) |
| `run` | string | Legacy install command (same as `steps[type=bash]`) |

### Full Hybrid Example (Kalshi)

```yaml
metadata:
  name: Kalshi
  bundle_id: org.deepshard.kalshi
  description: |
    Have Truffle trade and monitor Kalshi prediction markets for you.
  icon_file: ./icon.png

  background:
    process:
      cmd: ["python", "kalshi_background.py"]
      working_directory: /
      environment:
        PYTHONUNBUFFERED: "1"
        KALSHI_API_KEY: "REPLACE_WITH_KALSHI_API_KEY"
        KALSHI_PRIVATE_KEY: |
          REPLACE_WITH_KALSHI_PRIVATE_KEY_PEM
    default_schedule:
      type: interval
      interval:
        duration: 30m
        schedule:
          daily_window: "00:00-23:59"

  foreground:
    process:
      cmd: ["python", "kalshi_foreground.py"]
      working_directory: /
      environment:
        PYTHONUNBUFFERED: "1"
        KALSHI_API_KEY: "REPLACE_WITH_KALSHI_API_KEY"
        KALSHI_PRIVATE_KEY: |
          REPLACE_WITH_KALSHI_PRIVATE_KEY_PEM

steps:
  - name: Install dependencies
    type: bash
    run: |
      apk add --no-cache gcc musl-dev libffi-dev openssl-dev
      pip install --no-cache-dir "httpx>=0.27.0" "cryptography>=42.0.0"
  - name: Copy application files
    type: files
    files:
      - source: ./config.py
        destination: ./config.py
      - source: ./client.py
        destination: ./client.py
      - source: ./bg_worker.py
        destination: ./bg_worker.py
      - source: ./kalshi_foreground.py
        destination: ./kalshi_foreground.py
      - source: ./kalshi_background.py
        destination: ./kalshi_background.py
```

### Background-Only Example (Reddit)

```yaml
metadata:
  name: Reddit
  bundle_id: org.deepshard.reddit
  description: |
    Have your Truffle browse Reddit and post relevant content to your feed.
  background:
    process:
      cmd: ["python", "/opt/reddit.py"]
      working_directory: /
      environment:
        PYTHONUNBUFFERED: "1"
        SUBREDDITS: "news,worldnews,technology"
        USER_FEED_URL: "none"
    default_schedule:
      type: interval
      interval:
        duration: 60m
        schedule:
          daily_window: "00:00-23:59"
  icon_file: ./icon.png

steps:
  - name: Install dependencies
    type: bash
    run: |
      pip install --no-cache-dir --force-reinstall requests feedparser trafilatura==2.0.0 tld==0.13.1
  - name: Copy application files
    type: files
    files:
      - source: ./reddit.py
        destination: ./opt/reddit.py
```

---

## 4. Scheduling System

Background apps require a `default_schedule` defining when the BG process runs. Three schedule types are supported, parsed into `BackgroundAppRuntimePolicy` protobuf messages.

### type: interval

Run every N duration within optional daily/weekly windows.

```yaml
default_schedule:
  type: interval
  interval:
    duration: 30m          # required: ms/s/m/h/d
    schedule:              # optional constraints
      daily_window: "09:00-17:00"  # or {start: "09:00", end: "17:00"}
      allowed_days: [mon, tue, wed, thu, fri]
      # OR forbidden_days: [sat, sun]  (never both)
```

### type: times

Run at specific times of day with optional day filtering.

```yaml
default_schedule:
  type: times
  times:
    run_times: ["08:00", "12:00", "18:00"]
    allowed_days: [mon, wed, fri]
    # OR forbidden_days: [sun]
```

### type: always

Continuously running background process.

```yaml
default_schedule:
  type: always
```

### Parsing Details

- **Duration format**: integer + unit. Supported units: `ms`, `s`, `m`, `h`, `d`. Examples: `30m`, `2h`, `500ms`, `1d`.
- **Daily window**: string `"HH:MM-HH:MM"` or object `{start, end}`. Supports optional seconds `HH:MM:SS`.
- **Day filtering**: provide ONE of `allowed_days` or `forbidden_days` (never both). Values: `sun`/`mon`/`tue`/`wed`/`thu`/`fri`/`sat`.
- **Day mask encoding**: 7-bit bitmask where sat=bit0, fri=bit1, thu=bit2, wed=bit3, tue=bit4, mon=bit5, sun=bit6. The mask stores FORBIDDEN days (bits set = days excluded).
- **Default fallback**: if no schedule is provided for a BG app at deploy time, the SDK defaults to interval with 60s duration.

---

## 5. CLI Commands

All commands are dispatched from `cli.py` (~92K lines).

| Command | Description |
|---------|-------------|
| `truffile scan` | mDNS scan for Truffle devices on local network. Interactive device selection. |
| `truffile connect <device>` | Connect to a named device (e.g. `truffle-6272`). Prompts for User ID on first connect, requires device-side approval. |
| `truffile disconnect <device\|all>` | Clear saved credentials for one or all devices. |
| `truffile create [name]` | Scaffold a hybrid app starter with `truffile.yaml`, foreground/background Python files, and icon. |
| `truffile validate [path]` | Validate `truffile.yaml` + check Python syntax on all referenced `.py` files. |
| `truffile deploy [path]` | Full deploy: validate -> start build session -> upload files -> run bash steps -> finish app. |
| `truffile deploy --dry-run [path]` | Show deploy plan without mutating the device. |
| `truffile deploy -i [path]` | Deploy with interactive terminal into build container (debug mode). Can install Claude Code inside! |
| `truffile list apps` | List all installed apps on connected device. |
| `truffile list devices` | List all devices with saved credentials. |
| `truffile delete` | Delete installed apps from connected device (interactive selection). |
| `truffile models` | `GET /if2/v1/models` -- list models available on device. |
| `truffile chat` | Interactive REPL. All config via slash commands (see Inference section). |

---

## 6. Inference & Chat

Truffle exposes OpenAI-compatible inference endpoints at `/if2/v1/*`. The CLI provides a full-featured chat REPL with MCP integration, image attachments, and runtime configuration.

### HTTP Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/if2/v1/models` | List available models on device |
| `POST` | `/if2/v1/chat/completions` | Chat completion (streaming supported) |

### Chat REPL Commands

#### Core

| Command | Description |
|---------|-------------|
| `/help` or `/` | Show all available commands |
| `/history` | Show conversation history summary |
| `/reset` | Clear conversation state |
| `/models` | Model picker -- switch active model |
| `/attach <path\|url>` | Attach image for next message (local file or http(s) URL). Cleared after send. |
| `/config` | Show current chat settings |
| `/exit` or `/quit` | Exit chat |

#### Generation Controls

| Command | Description |
|---------|-------------|
| `/reasoning on\|off` | Toggle reasoning output |
| `/stream on\|off` | Toggle streaming |
| `/json on\|off` | Toggle JSON response mode |
| `/tools on\|off` | Toggle built-in tools (`web_search`, `web_fetch`) |
| `/max_tokens <int>` | Set max output tokens |
| `/temperature <float\|off>` | Set/clear temperature |
| `/top_p <float\|off>` | Set/clear top-p |
| `/max_rounds <int>` | Max assistant/tool loop rounds |
| `/system <text>` | Set system prompt |
| `/system clear` | Clear system prompt |

#### MCP in Chat

| Command | Description |
|---------|-------------|
| `/mcp connect <streamable-http-url>` | Connect external MCP server |
| `/mcp tools` | List discovered MCP tools |
| `/mcp status` | Show endpoint + tool count |
| `/mcp disconnect` | Disconnect MCP session |

### Direct HTTP Usage

```bash
# List models
curl -sS http://<device-host>/if2/v1/models

# Chat completion
curl -sS http://<device-host>/if2/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "<model-id-or-uuid>",
    "messages": [
      {"role": "user", "content": "Give me one sentence about Truffle."}
    ]
  }'
```

---

## 7. Deploy Pipeline

Deploy uses a builder session over gRPC + HTTP. The pipeline validates config, opens a containerized build environment, uploads files, runs install commands, and finalizes the app.

### Step-by-Step

1. **Validate** -- `validate_app_dir()` checks: truffile.yaml exists, parses YAML, validates `metadata.name`, detects app type (focus/ambient/hybrid), validates all process configs (cmd is non-empty list[str], env keys match regex, working_directory is string), checks icon file exists, syntax-checks all `.py` files referenced in file steps.

2. **Build Plan** -- `build_deploy_plan()` extracts: name, bundle_id, description, icon path, fg/bg process payloads (cmd normalized to `/usr/bin/` prefix, args, cwd, env as `KEY=VALUE` list), schedule config, file upload list, bash command list.

3. **Connect** -- `TruffleClient.connect()` opens gRPC `insecure_channel` to device address with 15s timeout.

4. **Start Build** -- `Builder_StartBuildSession` RPC. Returns `app_uuid` and `access_path`. Waits up to 45s for container to be ready (polls with `echo ready`).

5. **Upload Files** -- HTTP POST to `{http_base}/upload` with multipart file + `path` query param. Returns path, byte count, sha256. Retries 5x with linear backoff on 503.

6. **Run Bash Steps** -- HTTP POST to `{http_base}/exec/stream` (SSE). Commands wrapped in `bash -lc "cd {cwd} && {cmd}"`. Streams `log` events + `exit` code. Fails deploy on non-zero exit.

7. **Interactive (optional)** -- If `-i` flag: opens WebSocket terminal at `{http_base}/term`. User can debug, install deps, even install Claude Code. `exit` or Ctrl+D continues deploy.

8. **Finish App** -- `Builder_FinishBuildSession` RPC. Sets metadata (name, bundle_id, description, icon PNG data), foreground process config, background process config + `runtime_policy`. If BG app has no schedule, defaults to 60s interval.

### CLI Flow

```bash
truffile validate ./my-app        # Step 1
truffile deploy --dry-run ./my-app # Steps 1-2 (plan only)
truffile deploy ./my-app           # Steps 1-8
truffile deploy -i ./my-app        # Steps 1-8 with interactive shell at step 7
```

---

## 8. Transport Layer

`TruffleClient` (in `truffile/transport/client.py`) manages both the gRPC channel and HTTP/SSE connections.

### gRPC Methods (TruffleOS service)

| Method | Description |
|--------|-------------|
| `System_GetInfo` | Auth check (empty request, tests token validity) |
| `Client_RegisterNewSession` | Register new session with `user_id` + `ClientMetadata`. Returns session token. |
| `Apps_GetAll` | List all installed apps |
| `Apps_DeleteApp` | Delete app by UUID |
| `Builder_StartBuildSession` | Start build. Returns `app_uuid` + `access_path`. |
| `Builder_FinishBuildSession` | Finalize or discard build. Carries full app config (metadata, fg/bg process, runtime policy). |

### HTTP/SSE/WS Endpoints (build containers)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/containers/{access_path}/upload` | Multipart file upload (`path` query param). Returns `{path, bytes, sha256}`. |
| `POST` | `/containers/{access_path}/exec/stream` | SSE command execution. Body: `{cmd, cwd}`. Events: `log` (line content), `exit` (code). |
| `WS` | `/containers/{access_path}/term` | Interactive terminal WebSocket |

### Key Implementation Details

- **Client metadata**: Sent with `Client_RegisterNewSession`. Contains: `device` (hostname), `platform` (platform string), `version` (`truffile-{ver}-{python_ver}`).
- **mDNS resolution**: Hostnames containing `.local` are resolved via `socket.gethostbyname` in executor.
- **Retry policy**: All HTTP operations (upload, exec, exec_stream) retry 5x with linear backoff on 503.
- **Auth**: All gRPC calls include `("session", token)` metadata tuple.
- **SSE parsing**: Custom SSE parser in `_sse_events()` handles `event:` and `data:` fields, yields `(event_type, data)` tuples.
- **Command wrapping**: Exec commands wrapped as `bash -lc "cd {cwd} && {cmd}"`.
- **Cmd normalization**: First element of `cmd` list gets `/usr/bin/` prefix if not already absolute path.
- **Env normalization**: Environment dict converted to `["KEY=VALUE", ...]` list for protobuf.

### Credential Storage

`StorageService` (in `truffile/storage.py`) persists credentials in `~/.local/share/truffile/state.json`:

```json
{
  "devices": [{"name": "truffle-6272", "token": "..."}],
  "last_used_device": "truffle-6272",
  "client_user_id": "..."
}
```

Operations: `get_token`, `set_token`, `has_token`, `set_last_used`, `remove_device`, `clear_all`, `list_devices`.

---

## 9. Proto / gRPC Surface

The `truffle/` directory contains vendored protobuf definitions generated from TruffleOS firmware. These define the full device API surface.

### truffle.os

| Proto | Description |
|-------|-------------|
| `truffleos` | Main service definition (TruffleOS stub with all RPCs) |
| `builder` | `StartBuildSession{Request,Response}`, `FinishBuildSession{Request,Response}`, `BuildSessionError` |
| `client_session` | `RegisterNewSession{Request,Response}`, `NewSessionStatus`, `NewSessionVerification`, `VerifyNewSessionRequest`, `UserRecoveryCodes` |
| `client_metadata` | `ClientMetadata` (device, platform, version) |
| `client_user` | `RegisterNewUser{Request,Response}`, `UserIDForToken{Request,Response}` |
| `client_state` | `ClientState`, `UpdateClientState{Request,Response}`, `GetClientState{Request,Response}`, `GetAllClientStates{Request,Response}` |
| `app_queries` | `GetAllApps{Request,Response}`, `DeleteApp{Request,Response}` |
| `background_feed` | `BackgroundFeedEntry`, `BackgroundFeedSubmission` |
| `background_feed_queries` | `GetBackgroundFeed{Request,Response}`, `GetLatestFeedEntryID{Request,Response}` |
| `proactivity` | `ProactiveAction`, `ApproveProactiveAction{Request,Response}`, `CancelProactiveAction{Request,Response}` |
| `notification` | `SubscribeToNotificationsRequest`, `Notification` |
| `task` | `Task`, `TaskNode`, `TasksList`, `StreamingTaskStepResult`, `TaskStreamUpdate` |
| `task_actions` | `NewTask`, `OpenTaskRequest`, `InterruptTaskRequest`, `TaskSetAvailableApps{Request,Response}`, `TaskTestExternalToolProvider{Request,Response}`, `TaskActionResponse` |
| `task_queries` | `GetTasksRequest`, `GetOneTaskRequest`, `GetTaskInfos{Request,Response}` |
| `task_search` | `SearchTasksRequest`, `TaskSearchResult`, `SearchTasksResponse` |
| `task_info` | Task info detail messages |
| `task_step` | Task step detail messages |
| `task_user_response` | `UserMessage`, `PendingUserResponse`, `RespondToTaskRequest` |
| `task_target` | Task target definitions |
| `task_options` | Task execution options |
| `task_error` | Task error reporting |
| `hardware_stats` | `HardwareStats`, `HardwareStatsRequest` (CPU/memory/disk/GPU) |
| `hardware_info` | Hardware information |
| `hardware_control` | `HardwarePowerControl{Request,Response}` (shutdown/reboot) |
| `hardware_network` | Network configuration |
| `hardware_settings` | Hardware settings |
| `system_info` | `FirmwareVersion`, `SystemInfo`, `SystemCheckForUpdate{Request,Response}`, `SystemGetID{Request,Response}` |
| `system_settings` | `SystemSettings`, `TaskSettings` |
| `installer` | App installation management (large proto) |

### truffle.app

| Proto | Description |
|-------|-------------|
| `app` | `App` message (the core app model) |
| `app_build` | `ProcessConfig` (cmd, args, env, cwd) |
| `app_install` | App installation service |
| `app_runtime` | App runtime service (gRPC) |
| `background` | `BackgroundApp`, `BackgroundAppRuntimePolicy` (Interval/SpecificTimes/Always), `BackgroundContext` (priority: UNSPECIFIED/LOW/HIGH), `BackgroundAppSubmitContext{Request,Response}`, `BackgroundAppOnRun{Request,Response}`, `BackgroundAppYield{Request,Response}`, `BackgroundAppReportErrorResponse` |
| `foreground` | `ForegroundApp` definition |
| `default_app_manifest` | Default app manifest |

### truffle.common

| Proto | Description |
|-------|-------------|
| `content` | Content message types |
| `file` | File references |
| `icon` | `Icon` (png_data bytes) |
| `tool_provider` | Tool provider definitions |

---

## 10. App Store Examples

### Kalshi (Hybrid: FG + BG)

Path: `app-store/kalshi/`

**Files:**
- `truffile.yaml` -- Full hybrid config with both foreground + background process blocks, secrets via env vars, 30m interval schedule
- `kalshi_foreground.py` -- MCP server exposing tools: `get_markets`, `get_market`, `get_orderbook`, `get_positions`, `create_order`, `cancel_order`, `batch_cancel_orders`, `kalshi_health`
- `kalshi_background.py` -- Scheduled worker that generates portfolio summaries, price movement alerts, settlement alerts, order status updates, feed digests. Submits with priority (LOW/DEFAULT/HIGH).
- `bg_worker.py` -- `KalshiBackgroundWorker` class: API client + context generation logic
- `client.py` -- `KalshiClient`: HTTP API wrapper with auth (API key + PEM private key signing)
- `config.py` -- Configuration constants
- `icon.png` -- App icon (required for deploy)

**Key Patterns:**
- `atexit.register(_cleanup)` in both fg and bg for clean shutdown
- Structured success/error payloads from tools (not plain strings)
- Explicit tool descriptions with typed parameters for model routing
- Priority-based context submission for proactivity quality

### Reddit (BG only)

Path: `app-store/reddit/`

**Files:**
- `truffile.yaml` -- Background-only config, 60m interval, env vars for subreddit list and optional personal feed URL
- `reddit.py` -- Fetches from subreddits and/or personal feed, extracts article content via trafilatura, submits context
- `icon.png` -- App icon

**Key Patterns:**
- Background-only app pattern (no foreground block)
- Environment-driven configuration (`SUBREDDITS`, `USER_FEED_URL`)
- Dependencies installed via `apk` + `pip` in bash step

### Contributing

Submit apps via PR to `app-store/` folder with a screen recording. Accepted apps get deployed to the Truffle App Store with author credit.

---

## 11. Critical Patterns

### Clean Shutdown (REQUIRED)

Register `atexit.register(_cleanup)` in BOTH foreground and background scripts. In `_cleanup()`, close all HTTP clients, event loops, and outbound connections. Failing to do this causes flaky reruns and container crashes.

```python
import atexit

_api = None

def _cleanup():
    if _api:
        asyncio.get_event_loop().run_until_complete(_api.close())

atexit.register(_cleanup)
```

### MCP Transport (Foreground)

Foreground apps MUST serve MCP over `streamable-http`. `stdio` transport is NOT supported for deployed foreground apps. Use `create_mcp_server()` + `run_mcp_server()` from `app_runtime.mcp`.

```python
from app_runtime.mcp import create_mcp_server, run_mcp_server

mcp = create_mcp_server("my_app")

@mcp.tool("my_tool", description="Clear description with parameter docs")
async def my_tool(param: str) -> dict:
    return {"status": "ok", "data": result}

def main() -> None:
    run_mcp_server(mcp, logger)
```

### Rich Background Context

Submit structured, entity-rich context with concrete values. `"Price alert: FED-RATE-SEP moved up 12c (was 41c, now 53c)"` is far better for proactivity than generic summaries. Include tickers, absolute values, deltas, timestamps, IDs.

```python
from app_runtime.background import BackgroundRunContext, run_background

def my_ambient(ctx: BackgroundRunContext) -> None:
    content = "Price alert: TICKER moved +12c (41c -> 53c)"
    ctx.bg.submit_context(
        content=content,
        uris=[],
        priority="HIGH"  # LOW, DEFAULT, HIGH
    )

if __name__ == "__main__":
    run_background(my_ambient)
```

### Tool Description Quality

Tool descriptions are what the model uses for routing. Be explicit about what each tool does, document every parameter, and include example usage. This directly affects whether Truffle calls the right tool.

### Validation Before Deploy

Always run: `validate` -> `deploy --dry-run` -> `deploy`. The validator catches: missing truffile.yaml, invalid YAML, missing required fields, bad process configs, missing source files, Python syntax errors in referenced `.py` files.

### Secrets Handling

Secrets go in `metadata.*.process.environment`. Use YAML literal block style (`|`) for multiline values like PEM keys. Never commit real keys to source.

---

## 12. Coming Soon (per docs)

- Additional MCP assets: resources, prompts, files, and skills
- Tool icons and richer tool metadata
- Read-only tool semantics
- Tool-driven user elicitation (requesting user input from a tool flow)
- Expanded authentication and session handling for stateful MCP servers
- Runtime log viewing for background apps via SDK

---

## Quick Reference: App Scaffold

`truffile create my_app` generates:

- `truffile.yaml` with foreground + background process config
- `my_app_foreground.py` (MCP server stub)
- `my_app_background.py` (background context stub)
- `icon.png` (copied from docs/Truffle.png)
- Copy-file steps for both scripts

### Minimal Foreground-Only App

```yaml
metadata:
  name: MyTool
  bundle_id: com.me.mytool
  icon_file: ./icon.png
  foreground:
    process:
      cmd: ["python", "main.py"]
      working_directory: /

steps:
  - name: Install deps
    type: bash
    run: pip install --no-cache-dir httpx
  - name: Copy files
    type: files
    files:
      - source: ./main.py
        destination: ./main.py
```

### Minimal Background-Only App

```yaml
metadata:
  name: MyMonitor
  bundle_id: com.me.mymonitor
  icon_file: ./icon.png
  background:
    process:
      cmd: ["python", "monitor.py"]
      working_directory: /
    default_schedule:
      type: interval
      interval:
        duration: 15m

steps:
  - name: Copy files
    type: files
    files:
      - source: ./monitor.py
        destination: ./monitor.py
```
