"""Tailscale machine discovery.

Detects machines on the tailnet that could be added to the fleet.
Uses 'tailscale status --json' when available.
"""

from __future__ import annotations

import json
import subprocess


class TailscaleError(Exception):
    """Raised when Tailscale is not available or not running."""


def _extract_ipv4(tailscale_ips: list[str]) -> str | None:
    """Extract the first IPv4 address from a TailscaleIPs list."""
    for ip in tailscale_ips:
        if ":" not in ip:
            return ip
    return None


def _parse_node(node: dict) -> dict | None:
    """Extract machine info from a Tailscale status node."""
    hostname = node.get("HostName", "")
    ips = node.get("TailscaleIPs", [])
    os_name = node.get("OS", "")
    online = node.get("Online", False)

    ipv4 = _extract_ipv4(ips)
    if not hostname or not ipv4:
        return None

    return {
        "name": hostname,
        "tailscale_ip": ipv4,
        "os": os_name,
        "online": online,
    }


def discover_machines() -> list[dict]:
    """Discover online machines on the local Tailscale network.

    Returns a list of dicts with keys: name, tailscale_ip, os, online.
    Only includes machines that are currently online.

    Raises:
        TailscaleError: If Tailscale CLI is not found, not logged in, or not running.
    """
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        raise TailscaleError(
            "Tailscale CLI not found. Install from https://tailscale.com/download"
        )
    except subprocess.TimeoutExpired:
        raise TailscaleError("Tailscale CLI timed out. Is the daemon running?")

    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "not logged in" in stderr or "needslogin" in stderr:
            raise TailscaleError(
                "Tailscale is not logged in. Run 'tailscale login' first."
            )
        raise TailscaleError(f"tailscale status failed: {result.stderr.strip()}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise TailscaleError(f"Failed to parse Tailscale JSON output: {e}")

    backend_state = data.get("BackendState", "")
    if backend_state != "Running":
        raise TailscaleError(
            f"Tailscale is not running (state: {backend_state}). "
            "Run 'tailscale up' to connect."
        )

    machines: list[dict] = []

    # Include the local machine (Self node)
    self_node = data.get("Self")
    if self_node:
        parsed = _parse_node(self_node)
        if parsed:
            # Self is always considered online
            parsed["online"] = True
            machines.append(parsed)

    # Include all peers
    peers = data.get("Peer") or {}
    for peer in peers.values():
        parsed = _parse_node(peer)
        if parsed:
            machines.append(parsed)

    # Filter to online only
    machines = [m for m in machines if m["online"]]

    return machines
