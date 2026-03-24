"""SSH helpers using paramiko.

Replaces v1's inline SSH client/exec pattern from control-server/server.py
with reusable utilities.
"""

from __future__ import annotations

import re
import socket

import paramiko


class SSHError(Exception):
    """Raised when SSH connection or command execution fails."""


def create_ssh_client(
    host: str, user: str, timeout: int = 10
) -> paramiko.SSHClient:
    """Create and connect an SSH client to the given host.

    Uses the SSH agent and default key locations for authentication.
    No password prompts.

    Args:
        host: Hostname or Tailscale IP address.
        user: SSH username.
        timeout: Connection timeout in seconds.

    Returns:
        Connected paramiko.SSHClient.

    Raises:
        SSHError: If connection fails for any reason.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            username=user,
            timeout=timeout,
            allow_agent=True,
            look_for_keys=True,
        )
    except paramiko.AuthenticationException:
        client.close()
        raise SSHError(
            f"Authentication failed for {user}@{host}. "
            "Ensure your SSH key is loaded in the agent or exists at ~/.ssh/id_ed25519"
        )
    except paramiko.SSHException as e:
        client.close()
        raise SSHError(f"SSH error connecting to {user}@{host}: {e}")
    except socket.timeout:
        client.close()
        raise SSHError(f"Connection to {host} timed out after {timeout}s")
    except OSError as e:
        client.close()
        raise SSHError(f"Cannot reach {host}: {e}")
    return client


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

    Raises:
        SSHError: If the command times out.
    """
    try:
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        exit_code = stdout.channel.recv_exit_status()
    except socket.timeout:
        raise SSHError(f"Command timed out after {timeout}s: {command}")
    return (out, err, exit_code)


def ssh_check_deps(client: paramiko.SSHClient) -> dict[str, bool]:
    """Check for required dependencies on a remote machine.

    Checks: python3 (>= 3.10), uv, claude CLI, nvidia-smi.

    Returns:
        Dict of {dep_name: is_available}.
    """
    deps: dict[str, bool] = {
        "python3": False,
        "python3_version_ok": False,
        "uv": False,
        "claude": False,
        "nvidia_smi": False,
    }

    # Python 3
    out, _err, rc = ssh_exec(client, "python3 --version")
    if rc == 0:
        deps["python3"] = True
        match = re.search(r"Python (\d+)\.(\d+)", out)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            deps["python3_version_ok"] = (major, minor) >= (3, 10)

    # uv
    _out, _err, rc = ssh_exec(client, "uv --version")
    deps["uv"] = rc == 0

    # Claude Code CLI
    _out, _err, rc = ssh_exec(client, "claude --version")
    deps["claude"] = rc == 0

    # nvidia-smi (GPU present)
    _out, _err, rc = ssh_exec(client, "nvidia-smi")
    deps["nvidia_smi"] = rc == 0

    return deps


def detect_gpu(client: paramiko.SSHClient) -> tuple[str, int] | None:
    """Detect GPU model and VRAM via nvidia-smi.

    Returns:
        Tuple of (gpu_name, vram_gb) or None if no GPU / detection fails.
    """
    out, _err, rc = ssh_exec(
        client,
        "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits",
    )
    if rc != 0 or not out:
        return None

    try:
        # Take first GPU line: "NVIDIA GeForce RTX 4090, 24564"
        first_line = out.splitlines()[0]
        parts = first_line.split(", ")
        if len(parts) < 2:
            return None
        gpu_name = parts[0]
        # Strip common prefixes for cleaner names
        for prefix in ("NVIDIA GeForce ", "NVIDIA "):
            if gpu_name.startswith(prefix):
                gpu_name = gpu_name[len(prefix):]
                break
        vram_mib = int(parts[1].strip())
        vram_gb = round(vram_mib / 1024)
        if vram_gb < 1:
            vram_gb = 1
        return (gpu_name, vram_gb)
    except (ValueError, IndexError):
        return None


def close_ssh_client(client: paramiko.SSHClient) -> None:
    """Close an SSH client connection, ignoring errors."""
    try:
        client.close()
    except Exception:
        pass
