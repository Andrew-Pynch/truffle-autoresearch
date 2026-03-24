"""SSH helpers using paramiko.

Replaces v1's inline SSH client/exec pattern from control-server/server.py
with reusable utilities.
"""

from __future__ import annotations

import paramiko


def create_ssh_client(
    host: str, user: str, key_path: str | None = None
) -> paramiko.SSHClient:
    """Create and connect an SSH client to the given host.

    Args:
        host: Hostname or IP address.
        user: SSH username.
        key_path: Path to SSH private key. Defaults to ~/.ssh/id_ed25519.

    Returns:
        Connected paramiko.SSHClient.
    """
    raise NotImplementedError


def ssh_exec(
    client: paramiko.SSHClient, command: str, timeout: int = 30
) -> tuple[str, str, int]:
    """Execute a command over SSH.

    Args:
        client: Connected SSH client.
        command: Shell command to run.
        timeout: Command timeout in seconds.

    Returns:
        Tuple of (stdout, stderr, exit_code).
    """
    raise NotImplementedError
