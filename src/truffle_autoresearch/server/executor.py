"""Machine command execution — local subprocess or remote SSH."""

from __future__ import annotations

import shlex
import subprocess

import paramiko

from truffle_autoresearch.config.fleet import FleetConfig, MachineConfig
from truffle_autoresearch.fleet.ssh import (
    close_ssh_client,
    create_ssh_client,
    ssh_exec,
)


class ExecutorError(Exception):
    """Raised when command execution setup fails."""


class MachineExecutor:
    """Runs commands on fleet machines — local subprocess or remote SSH."""

    def __init__(self, fleet_config: FleetConfig) -> None:
        self._fleet = fleet_config
        self._local_machine = fleet_config.host.machine
        self._machines = {m.name: m for m in fleet_config.machines}
        self._ssh_clients: dict[str, paramiko.SSHClient] = {}

    def _get_machine(self, machine_name: str) -> MachineConfig:
        if machine_name not in self._machines:
            raise ExecutorError(
                f"Unknown machine: {machine_name}. "
                f"Available: {sorted(self._machines.keys())}"
            )
        return self._machines[machine_name]

    def _is_local(self, machine_name: str) -> bool:
        return machine_name == self._local_machine

    def _get_ssh_client(self, machine: MachineConfig) -> paramiko.SSHClient:
        cached = self._ssh_clients.get(machine.name)
        if cached is not None:
            transport = cached.get_transport()
            if transport is not None and transport.is_active():
                return cached
            close_ssh_client(cached)

        client = create_ssh_client(machine.tailscale_ip, machine.ssh_user)
        self._ssh_clients[machine.name] = client
        return client

    def execute(
        self, machine_name: str, command: str, timeout: int = 30
    ) -> tuple[str, str, int]:
        """Run a command on a machine. Returns (stdout, stderr, exit_code)."""
        machine = self._get_machine(machine_name)
        if self._is_local(machine_name):
            return self._local_exec(command, timeout)
        return self._remote_exec(machine, command, timeout)

    def _local_exec(
        self, command: str, timeout: int
    ) -> tuple[str, str, int]:
        try:
            r = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return (r.stdout.strip(), r.stderr.strip(), r.returncode)
        except subprocess.TimeoutExpired:
            return ("", f"Command timed out after {timeout}s", 1)

    def _remote_exec(
        self, machine: MachineConfig, command: str, timeout: int
    ) -> tuple[str, str, int]:
        client = self._get_ssh_client(machine)
        try:
            return ssh_exec(client, command, timeout)
        except Exception:
            # Connection may have gone stale between check and use — retry once
            close_ssh_client(client)
            self._ssh_clients.pop(machine.name, None)
            client = self._get_ssh_client(machine)
            return ssh_exec(client, command, timeout)

    def read_file(
        self, machine_name: str, path: str, tail: int | None = None
    ) -> str:
        """Read a file from a machine. If tail is set, return last N lines."""
        if tail is not None:
            cmd = f"tail -{tail} {shlex.quote(path)}"
        else:
            cmd = f"cat {shlex.quote(path)}"
        stdout, _stderr, _code = self.execute(machine_name, cmd)
        return stdout

    def tmux_start(
        self, machine_name: str, session_name: str, command: str
    ) -> bool:
        """Start a tmux session with the given command."""
        cmd = f"tmux new-session -d -s {shlex.quote(session_name)} {shlex.quote(command)}"
        _out, _err, code = self.execute(machine_name, cmd)
        return code == 0

    def tmux_running(self, machine_name: str, session_name: str) -> bool:
        """Check if a tmux session exists."""
        cmd = f"tmux has-session -t {shlex.quote(session_name)} 2>/dev/null"
        _out, _err, code = self.execute(machine_name, cmd)
        return code == 0

    def tmux_kill(self, machine_name: str, session_name: str) -> bool:
        """Kill a tmux session."""
        cmd = f"tmux kill-session -t {shlex.quote(session_name)} 2>/dev/null"
        _out, _err, code = self.execute(machine_name, cmd)
        return code == 0

    def close(self) -> None:
        """Close all cached SSH clients."""
        for client in self._ssh_clients.values():
            close_ssh_client(client)
        self._ssh_clients.clear()
