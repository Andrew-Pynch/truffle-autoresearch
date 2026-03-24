"""Truffle app deployment.

Handles packaging and deploying the autoresearch coordinator
to a Truffle device, replacing v1's manual 'truffile deploy' workflow.
"""

from __future__ import annotations


def deploy_truffle_app(device_id: str) -> None:
    """Deploy the autoresearch coordinator to the specified Truffle device.

    Args:
        device_id: Truffle device ID (e.g., 'truffle-7197').
    """
    raise NotImplementedError
