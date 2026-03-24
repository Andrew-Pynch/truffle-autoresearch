"""Interactive fleet initialization wizard.

Guides the user through creating ~/.autoresearch/fleet.yaml
by discovering machines, selecting a host, and configuring Truffle.
"""

from __future__ import annotations

import getpass
from pathlib import Path

import typer
import yaml
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from truffle_autoresearch.config.fleet import (
    FleetConfig,
    HostConfig,
    MachineConfig,
    TruffleConfig,
)
from truffle_autoresearch.config.paths import AUTORESEARCH_DIR, FLEET_CONFIG_PATH
from truffle_autoresearch.fleet.discovery import TailscaleError, discover_machines
from truffle_autoresearch.fleet.ssh import (
    SSHError,
    close_ssh_client,
    create_ssh_client,
    detect_gpu,
    ssh_check_deps,
)


def save_fleet_config(config: FleetConfig, path: Path | None = None) -> None:
    """Serialize and write a FleetConfig to YAML.

    Creates the parent directory if it doesn't exist.
    """
    config_path = path or FLEET_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="python")
    if data.get("truffle") is None:
        del data["truffle"]
    config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def _prompt_int(message: str, min_val: int = 1) -> int:
    """Prompt for an integer with validation."""
    while True:
        raw = typer.prompt(message)
        try:
            val = int(raw)
            if val < min_val:
                rprint(f"[red]Must be at least {min_val}.[/red]")
                continue
            return val
        except ValueError:
            rprint("[red]Please enter a valid number.[/red]")


def _select_machines(machines: list[dict]) -> list[dict]:
    """Prompt user to multi-select machines by number."""
    while True:
        raw = typer.prompt(
            "Select machines by number (comma-separated, e.g. 1,3,4, or 'all')"
        )
        if raw.strip().lower() == "all":
            return list(machines)
        try:
            indices = [int(x.strip()) for x in raw.split(",")]
        except ValueError:
            rprint("[red]Invalid input. Enter comma-separated numbers.[/red]")
            continue
        if any(i < 1 or i > len(machines) for i in indices):
            rprint(f"[red]Numbers must be between 1 and {len(machines)}.[/red]")
            continue
        if not indices:
            rprint("[red]Select at least one machine.[/red]")
            continue
        return [machines[i - 1] for i in indices]


def _show_deps_table(name: str, deps: dict[str, bool]) -> None:
    """Display a dependency check results table for one machine."""
    table = Table(title=f"Dependencies on {name}")
    table.add_column("Dependency", style="cyan")
    table.add_column("Status")

    labels = {
        "python3": "Python 3",
        "python3_version_ok": "Python >= 3.10",
        "uv": "uv",
        "claude": "Claude Code CLI",
        "nvidia_smi": "nvidia-smi (GPU)",
    }
    for key, label in labels.items():
        ok = deps.get(key, False)
        status = "[green]found[/green]" if ok else "[red]missing[/red]"
        table.add_row(label, status)

    rprint(table)


def _configure_machine(machine: dict) -> MachineConfig | None:
    """Configure a single machine: test SSH, check deps, detect GPU.

    Returns MachineConfig or None if the user chooses to skip.
    """
    name = machine["name"]
    ip = machine["tailscale_ip"]
    rprint(f"\n[bold]Configuring {name}[/bold] ({ip})")

    default_user = getpass.getuser()
    ssh_user = typer.prompt(f"  SSH user for {name}", default=default_user)

    # Test SSH connection
    rprint(f"  Testing SSH connection to {ssh_user}@{ip}...")
    try:
        client = create_ssh_client(ip, ssh_user)
    except SSHError as e:
        rprint(f"  [red]SSH failed: {e}[/red]")
        if typer.confirm("  Skip this machine?", default=True):
            return None
        return None

    # Check dependencies
    rprint("  Checking dependencies...")
    deps = ssh_check_deps(client)
    _show_deps_table(name, deps)

    missing = []
    if not deps["python3_version_ok"]:
        missing.append("Python >= 3.10")
    if not deps["uv"]:
        missing.append("uv")
    if not deps["claude"]:
        missing.append("Claude Code CLI")
    if missing:
        rprint(f"  [yellow]Warning: missing {', '.join(missing)}[/yellow]")

    # Detect GPU
    gpu_info = detect_gpu(client)
    close_ssh_client(client)

    if gpu_info:
        gpu_name, vram_gb = gpu_info
        rprint(f"  [green]Detected GPU: {gpu_name} ({vram_gb} GB)[/green]")
        if not typer.confirm("  Use detected GPU info?", default=True):
            gpu_name = typer.prompt("  GPU model (e.g. 'RTX 4090')")
            vram_gb = _prompt_int("  VRAM in GB")
    else:
        rprint("  [yellow]No GPU detected via nvidia-smi.[/yellow]")
        gpu_name = typer.prompt("  GPU model (e.g. 'RTX 4090')")
        vram_gb = _prompt_int("  VRAM in GB")

    return MachineConfig(
        name=name,
        tailscale_ip=ip,
        ssh_user=ssh_user,
        gpu=gpu_name,
        vram_gb=vram_gb,
    )


def run_init_wizard() -> None:
    """Run the interactive fleet init wizard.

    Creates ~/.autoresearch/ directory and fleet.yaml with user input.
    """
    rprint(Panel("[bold]Autoresearch Fleet Setup[/bold]", expand=False))

    # Phase 0: Check for existing config
    if FLEET_CONFIG_PATH.exists():
        rprint(
            f"[yellow]Fleet config already exists at {FLEET_CONFIG_PATH}[/yellow]"
        )
        if not typer.confirm("Overwrite existing fleet.yaml?", default=False):
            rprint("[yellow]Aborted.[/yellow]")
            return

    # Phase 1: Discover Tailscale machines
    rprint("\nDiscovering machines on Tailscale network...")
    try:
        machines = discover_machines()
    except TailscaleError as e:
        rprint(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not machines:
        rprint("[red]No online machines found on Tailscale network.[/red]")
        raise typer.Exit(1)

    # Phase 2: Display discovered machines
    table = Table(title="Discovered Machines")
    table.add_column("#", style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Tailscale IP", style="green")
    table.add_column("OS")
    for i, m in enumerate(machines, 1):
        table.add_row(str(i), m["name"], m["tailscale_ip"], m["os"])
    rprint(table)

    # Phase 3: Select machines
    selected = _select_machines(machines)
    rprint(f"\nSelected {len(selected)} machine(s).\n")

    # Phase 4: Configure each machine
    configured: list[MachineConfig] = []
    for machine in selected:
        mc = _configure_machine(machine)
        if mc:
            configured.append(mc)

    if not configured:
        rprint("[red]No machines were configured. Aborting.[/red]")
        raise typer.Exit(1)

    # Phase 5: Select host machine
    if len(configured) == 1:
        host_name = configured[0].name
        rprint(f"\n[bold]Host machine:[/bold] {host_name} (only machine)")
    else:
        rprint("\n[bold]Select the host machine[/bold] (runs control server + ngrok):")
        for i, mc in enumerate(configured, 1):
            rprint(f"  {i}. {mc.name}")
        while True:
            raw = typer.prompt("Host machine number")
            try:
                idx = int(raw)
                if 1 <= idx <= len(configured):
                    host_name = configured[idx - 1].name
                    break
                rprint(f"[red]Pick 1-{len(configured)}.[/red]")
            except ValueError:
                rprint("[red]Enter a number.[/red]")

    # Phase 6: Ngrok auth token
    ngrok_token = typer.prompt(
        "\nNgrok auth token (press Enter to skip)", default="", show_default=False
    )

    # Phase 7: Truffle integration
    truffle_config: TruffleConfig | None = None
    if typer.confirm("\nConfigure Truffle device integration?", default=False):
        device_id = typer.prompt("  Truffle device ID (e.g. 'truffle-7197')")
        truffle_config = TruffleConfig(device_id=device_id)

    # Phase 8: Build and save config
    config = FleetConfig(
        version=1,
        host=HostConfig(machine=host_name, ngrok_authtoken=ngrok_token),
        machines=configured,
        truffle=truffle_config,
    )

    AUTORESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    save_fleet_config(config)

    # Phase 9: Success summary
    summary_table = Table(title="Fleet Configuration")
    summary_table.add_column("Machine", style="cyan")
    summary_table.add_column("IP", style="green")
    summary_table.add_column("GPU")
    summary_table.add_column("Role")
    for mc in configured:
        role = "[bold]host[/bold]" if mc.name == host_name else "worker"
        summary_table.add_row(mc.name, mc.tailscale_ip, f"{mc.gpu} ({mc.vram_gb}GB)", role)

    rprint("\n")
    rprint(summary_table)
    if truffle_config:
        rprint(f"\nTruffle device: {truffle_config.device_id}")
    rprint(
        Panel(
            f"[green]Fleet config written to {FLEET_CONFIG_PATH}[/green]\n\n"
            "Next steps:\n"
            "  autoresearch status     — verify fleet connectivity\n"
            "  autoresearch add-target — add a research target\n"
            "  autoresearch run <target> — start a research loop",
            title="Setup Complete",
            expand=False,
        )
    )
