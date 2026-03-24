"""Fleet management package."""

from truffle_autoresearch.fleet.discovery import TailscaleError, discover_machines
from truffle_autoresearch.fleet.init_wizard import run_init_wizard, save_fleet_config
from truffle_autoresearch.fleet.ssh import (
    SSHError,
    close_ssh_client,
    create_ssh_client,
    detect_gpu,
    ssh_check_deps,
    ssh_exec,
)

__all__ = [
    "TailscaleError",
    "discover_machines",
    "run_init_wizard",
    "save_fleet_config",
    "SSHError",
    "close_ssh_client",
    "create_ssh_client",
    "detect_gpu",
    "ssh_check_deps",
    "ssh_exec",
]
