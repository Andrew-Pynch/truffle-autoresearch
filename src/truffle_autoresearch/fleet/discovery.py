"""Tailscale machine discovery.

Detects machines on the tailnet that could be added to the fleet.
Uses 'tailscale status --json' when available.
"""

from __future__ import annotations


async def discover_machines() -> list[dict]:
    """Discover machines on the local Tailscale network.

    Returns a list of dicts with keys: name, tailscale_ip, os, online.
    """
    raise NotImplementedError
