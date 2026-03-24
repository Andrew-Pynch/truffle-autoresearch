"""Data access layer — fetches experiment data from the control server API."""

import logging

import httpx

from config import CONTROL_SERVER_URL, CONTROL_SERVER_TOKEN

logger = logging.getLogger(__name__)

_API_HEADERS = {
    "Authorization": f"Bearer {CONTROL_SERVER_TOKEN}",
    "ngrok-skip-browser-warning": "true",
}

# Async client for foreground (MCP event loop)
_async_client: httpx.AsyncClient | None = None

# Sync client for background (called from sync run())
_sync_client: httpx.Client | None = None


def _get_async_client() -> httpx.AsyncClient:
    """Lazily create and return a shared async HTTP client."""
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers=_API_HEADERS,
        )
    return _async_client


def _get_sync_client() -> httpx.Client:
    """Lazily create and return a shared sync HTTP client."""
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(
            timeout=30.0, follow_redirects=True, headers=_API_HEADERS,
        )
    return _sync_client


def _api_url(path: str) -> str:
    """Build full API URL from a path like /api/status."""
    return f"{CONTROL_SERVER_URL}{path}"


def _extract_error(resp: httpx.Response) -> str:
    """Extract error detail from a non-2xx response."""
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    return f"HTTP {resp.status_code}: {detail}"


# ---------------------------------------------------------------------------
# Async functions (foreground / MCP tools)
# ---------------------------------------------------------------------------
async def get_status() -> dict:
    """GET /api/status — per-machine experiment count, best_val_bpb, researcher_running."""
    try:
        resp = await _get_async_client().get(_api_url("/api/status"))
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Request failed: {e}"}
    if resp.status_code != 200:
        return {"ok": False, "error": _extract_error(resp)}
    return {"ok": True, "status": resp.json()}


async def get_results(machine_name: str) -> dict:
    """GET /api/results/{machine} — full experiment list."""
    try:
        resp = await _get_async_client().get(_api_url(f"/api/results/{machine_name}"))
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Request failed for {machine_name}: {e}"}
    if resp.status_code != 200:
        return {"ok": False, "error": _extract_error(resp)}
    data = resp.json()
    return {"ok": True, "experiments": data.get("results", [])}


async def get_trajectory(machine_name: str) -> dict:
    """GET /api/results/{machine}/trajectory — chronological experiment list."""
    try:
        resp = await _get_async_client().get(
            _api_url(f"/api/results/{machine_name}/trajectory"),
        )
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Request failed for {machine_name}: {e}"}
    if resp.status_code != 200:
        return {"ok": False, "error": _extract_error(resp)}
    return {"ok": True, "trajectory": resp.json()}


async def get_researcher_logs(machine_name: str) -> dict:
    """GET /api/researcher/{machine}/logs — recent researcher log lines."""
    try:
        resp = await _get_async_client().get(
            _api_url(f"/api/researcher/{machine_name}/logs"),
        )
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Request failed for {machine_name}: {e}"}
    if resp.status_code != 200:
        return {"ok": False, "error": _extract_error(resp)}
    data = resp.json()
    return {"ok": True, "lines": data.get("lines", []), "log_file": data.get("log_file")}


async def start_researcher(machine_name: str) -> dict:
    """POST /api/researcher/{machine}/start — start the research loop."""
    try:
        resp = await _get_async_client().post(
            _api_url(f"/api/researcher/{machine_name}/start"),
        )
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Request failed for {machine_name}: {e}"}
    if resp.status_code not in (200, 201):
        return {"ok": False, "error": _extract_error(resp)}
    return {"ok": True, **resp.json()}


async def stop_researcher(machine_name: str) -> dict:
    """POST /api/researcher/{machine}/stop — stop the research loop."""
    try:
        resp = await _get_async_client().post(
            _api_url(f"/api/researcher/{machine_name}/stop"),
        )
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Request failed for {machine_name}: {e}"}
    if resp.status_code != 200:
        return {"ok": False, "error": _extract_error(resp)}
    return {"ok": True, **resp.json()}


async def sync_results(machine_name: str) -> dict:
    """POST /api/sync/{machine} — trigger result sync to GitHub."""
    try:
        resp = await _get_async_client().post(
            _api_url(f"/api/sync/{machine_name}"),
        )
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Request failed for {machine_name}: {e}"}
    if resp.status_code != 200:
        return {"ok": False, "error": _extract_error(resp)}
    return {"ok": True, **resp.json()}


# ---------------------------------------------------------------------------
# Sync functions (background coordinator)
# ---------------------------------------------------------------------------
def get_status_sync() -> dict:
    """GET /api/status (sync)."""
    try:
        resp = _get_sync_client().get(_api_url("/api/status"))
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Request failed: {e}"}
    if resp.status_code != 200:
        return {"ok": False, "error": _extract_error(resp)}
    return {"ok": True, "status": resp.json()}


def get_results_sync(machine_name: str) -> dict:
    """GET /api/results/{machine} (sync)."""
    try:
        resp = _get_sync_client().get(_api_url(f"/api/results/{machine_name}"))
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Request failed for {machine_name}: {e}"}
    if resp.status_code != 200:
        return {"ok": False, "error": _extract_error(resp)}
    data = resp.json()
    return {"ok": True, "experiments": data.get("results", [])}


def start_researcher_sync(machine_name: str) -> dict:
    """POST /api/researcher/{machine}/start (sync)."""
    try:
        resp = _get_sync_client().post(_api_url(f"/api/researcher/{machine_name}/start"))
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Request failed for {machine_name}: {e}"}
    if resp.status_code not in (200, 201):
        return {"ok": False, "error": _extract_error(resp)}
    return {"ok": True, **resp.json()}


def post_heartbeat_sync(timestamp: str, action: str, cycle: int) -> dict:
    """POST /api/truffle/heartbeat (sync)."""
    try:
        resp = _get_sync_client().post(
            _api_url("/api/truffle/heartbeat"),
            json={"timestamp": timestamp, "action": action, "cycle": cycle},
        )
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Heartbeat failed: {e}"}
    if resp.status_code != 200:
        return {"ok": False, "error": _extract_error(resp)}
    return {"ok": True}


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
async def close_async_client():
    """Close the shared async HTTP client if it exists."""
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None


def close_sync_client():
    """Close the shared sync HTTP client if it exists."""
    global _sync_client
    if _sync_client is not None:
        _sync_client.close()
        _sync_client = None
