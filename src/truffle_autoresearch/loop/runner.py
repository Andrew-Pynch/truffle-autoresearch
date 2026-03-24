"""Autoresearch loop orchestration.

Replaces v1's autoresearch_loop.sh with a Python implementation
that spawns Claude agent sessions, manages git branches,
syncs results, and handles restarts.
"""

from __future__ import annotations

from pathlib import Path

from truffle_autoresearch.config.fleet import FleetConfig, MachineConfig
from truffle_autoresearch.config.target import TargetConfig


class ResearchRunner:
    """Orchestrates the autoresearch loop for a target on a machine.

    Manages the cycle of: spawn agent -> run experiment -> log results ->
    sync to git -> repeat.
    """

    def __init__(
        self,
        target: TargetConfig,
        target_dir: Path,
        machine: MachineConfig,
        fleet: FleetConfig,
    ) -> None:
        self.target = target
        self.target_dir = target_dir
        self.machine = machine
        self.fleet = fleet

    async def start(self) -> None:
        """Start the research loop."""
        raise NotImplementedError

    async def stop(self) -> None:
        """Stop the research loop gracefully."""
        raise NotImplementedError

    def is_running(self) -> bool:
        """Check if the loop is currently running."""
        raise NotImplementedError
