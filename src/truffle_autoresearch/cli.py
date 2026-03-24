"""CLI entry point for autoresearch."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint

app = typer.Typer(
    name="autoresearch",
    help="Automated ML research on personal hardware, coordinated by a Truffle device.",
    no_args_is_help=True,
)


@app.command()
def init() -> None:
    """Initialize autoresearch: create ~/.autoresearch/ and fleet.yaml interactively."""
    from truffle_autoresearch.fleet.init_wizard import run_init_wizard

    run_init_wizard()


@app.command()
def add_machine() -> None:
    """Discover and add a new machine to the fleet."""
    import getpass

    from rich.table import Table

    from truffle_autoresearch.config.fleet import (
        ConfigError,
        FleetConfig,
        HostConfig,
        MachineConfig,
        load_fleet_config,
    )
    from truffle_autoresearch.fleet.discovery import TailscaleError, discover_machines
    from truffle_autoresearch.fleet.init_wizard import save_fleet_config
    from truffle_autoresearch.fleet.ssh import (
        SSHError,
        close_ssh_client,
        create_ssh_client,
        detect_gpu,
        ssh_check_deps,
    )

    # Load existing config
    try:
        config = load_fleet_config()
    except ConfigError:
        rprint("[red]No fleet config found. Run 'autoresearch init' first.[/red]")
        raise typer.Exit(1)

    # Discover machines not yet in fleet
    try:
        machines = discover_machines()
    except TailscaleError as e:
        rprint(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    existing_ips = {m.tailscale_ip for m in config.machines}
    available = [m for m in machines if m["tailscale_ip"] not in existing_ips]

    if not available:
        rprint("[green]All discovered machines are already in the fleet.[/green]")
        return

    # Show available machines
    table = Table(title="Available Machines (not yet in fleet)")
    table.add_column("#", style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Tailscale IP", style="green")
    table.add_column("OS")
    for i, m in enumerate(available, 1):
        table.add_row(str(i), m["name"], m["tailscale_ip"], m["os"])
    rprint(table)

    # Select one
    while True:
        raw = typer.prompt("Select a machine to add (number)")
        try:
            idx = int(raw)
            if 1 <= idx <= len(available):
                break
            rprint(f"[red]Pick 1-{len(available)}.[/red]")
        except ValueError:
            rprint("[red]Enter a number.[/red]")

    machine = available[idx - 1]
    name = machine["name"]
    ip = machine["tailscale_ip"]

    # Configure SSH
    ssh_user = typer.prompt(f"SSH user for {name}", default=getpass.getuser())

    rprint(f"Testing SSH connection to {ssh_user}@{ip}...")
    try:
        client = create_ssh_client(ip, ssh_user)
    except SSHError as e:
        rprint(f"[red]SSH failed: {e}[/red]")
        raise typer.Exit(1)

    # Check deps
    deps = ssh_check_deps(client)
    from truffle_autoresearch.fleet.init_wizard import _show_deps_table

    _show_deps_table(name, deps)

    # Detect GPU
    gpu_info = detect_gpu(client)
    close_ssh_client(client)

    if gpu_info:
        gpu_name, vram_gb = gpu_info
        rprint(f"[green]Detected GPU: {gpu_name} ({vram_gb} GB)[/green]")
        if not typer.confirm("Use detected GPU info?", default=True):
            gpu_name = typer.prompt("GPU model (e.g. 'RTX 4090')")
            vram_gb = int(typer.prompt("VRAM in GB"))
    else:
        rprint("[yellow]No GPU detected via nvidia-smi.[/yellow]")
        gpu_name = typer.prompt("GPU model (e.g. 'RTX 4090')")
        vram_gb = int(typer.prompt("VRAM in GB"))

    new_machine = MachineConfig(
        name=name,
        tailscale_ip=ip,
        ssh_user=ssh_user,
        gpu=gpu_name,
        vram_gb=vram_gb,
    )

    # Build new config (frozen models — must reconstruct)
    new_config = FleetConfig(
        version=config.version,
        host=config.host,
        machines=[*config.machines, new_machine],
        truffle=config.truffle,
    )
    save_fleet_config(new_config)
    rprint(f"\n[green]Added {name} to fleet.[/green]")


@app.command()
def remove_machine() -> None:
    """Remove a machine from the fleet."""
    from rich.table import Table

    from truffle_autoresearch.config.fleet import (
        ConfigError,
        FleetConfig,
        load_fleet_config,
    )
    from truffle_autoresearch.fleet.init_wizard import save_fleet_config

    try:
        config = load_fleet_config()
    except ConfigError:
        rprint("[red]No fleet config found. Run 'autoresearch init' first.[/red]")
        raise typer.Exit(1)

    if not config.machines:
        rprint("[yellow]No machines in fleet.[/yellow]")
        return

    # Show current machines
    table = Table(title="Current Fleet Machines")
    table.add_column("#", style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("IP", style="green")
    table.add_column("GPU")
    table.add_column("Role")
    for i, m in enumerate(config.machines, 1):
        role = "[bold]host[/bold]" if m.name == config.host.machine else ""
        table.add_row(str(i), m.name, m.tailscale_ip, f"{m.gpu} ({m.vram_gb}GB)", role)
    rprint(table)

    # Select one to remove
    while True:
        raw = typer.prompt("Select a machine to remove (number)")
        try:
            idx = int(raw)
            if 1 <= idx <= len(config.machines):
                break
            rprint(f"[red]Pick 1-{len(config.machines)}.[/red]")
        except ValueError:
            rprint("[red]Enter a number.[/red]")

    target = config.machines[idx - 1]

    if target.name == config.host.machine:
        rprint(
            f"[red]Cannot remove {target.name} — it is the host machine. "
            "Change the host first.[/red]"
        )
        raise typer.Exit(1)

    if not typer.confirm(f"Remove {target.name} from fleet?", default=False):
        rprint("[yellow]Aborted.[/yellow]")
        return

    remaining = [m for m in config.machines if m.name != target.name]
    new_config = FleetConfig(
        version=config.version,
        host=config.host,
        machines=remaining,
        truffle=config.truffle,
    )
    save_fleet_config(new_config)
    rprint(f"\n[green]Removed {target.name} from fleet.[/green]")


@app.command()
def add_target(
    name: str = typer.Argument(help="Target name (e.g., 'toy-lm')"),
    directory: Optional[Path] = typer.Option(None, help="Destination directory (default: ./<name>)"),
    builtin: bool = typer.Option(False, "--builtin", help="Copy a builtin target instead of scaffolding"),
) -> None:
    """Add a research target. Use --builtin to copy a shipped target."""
    from truffle_autoresearch.config.fleet import ConfigError
    from truffle_autoresearch.targets.loader import copy_builtin_target

    dest = directory or Path.cwd() / name
    try:
        if builtin:
            copy_builtin_target(name, dest)
            rprint(f"[green]Copied builtin target '{name}' to {dest}[/green]")
        else:
            copy_builtin_target("_skeleton", dest)
            # Replace the placeholder name with the actual target name
            target_yaml = dest / "target.yaml"
            content = target_yaml.read_text()
            content = content.replace("name: skeleton", f"name: {name}", 1)
            target_yaml.write_text(content)
            rprint(f"[green]Scaffolded new target '{name}' at {dest}[/green]")
        rprint(f"[dim]Edit {dest / 'target.yaml'} to configure your target.[/dim]")
    except ConfigError as e:
        rprint(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def list_targets() -> None:
    """List all available targets (builtin and user-configured)."""
    from rich.console import Console
    from rich.table import Table

    from truffle_autoresearch.targets.loader import find_targets, list_builtin_targets

    console = Console()

    # Local targets in current directory
    local = find_targets()
    if local:
        table = Table(title="Local Targets (current directory)")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("Metric", style="green")
        table.add_column("Direction")
        for _path, config in local:
            table.add_row(
                config.name,
                config.description,
                config.metric.name,
                config.metric.direction,
            )
        console.print(table)
    else:
        rprint("[dim]No local targets found in current directory.[/dim]")

    # Available builtins
    builtins = list_builtin_targets()
    if builtins:
        rprint()
        rprint("[bold]Available Builtin Targets:[/bold]")
        for bname in builtins:
            rprint(f"  [cyan]{bname}[/cyan]  (add with: autoresearch add-target --builtin {bname})")
    else:
        rprint("[dim]No builtin targets available.[/dim]")


@app.command()
def run(
    target: str = typer.Argument(help="Target name to run"),
    machine: Optional[str] = typer.Option(None, help="Specific machine (default: all)"),
) -> None:
    """Start the autoresearch loop on the given target."""
    rprint("[yellow]autoresearch run: not yet implemented[/yellow]")


@app.command()
def stop(
    target: Optional[str] = typer.Argument(None, help="Target to stop (default: all)"),
    machine: Optional[str] = typer.Option(None, help="Specific machine (default: all)"),
) -> None:
    """Stop running autoresearch loops."""
    rprint("[yellow]autoresearch stop: not yet implemented[/yellow]")


@app.command()
def status() -> None:
    """Show status of all running experiments across the fleet."""
    rprint("[yellow]autoresearch status: not yet implemented[/yellow]")


@app.command()
def dashboard() -> None:
    """Launch the web dashboard (FastAPI server + static frontend)."""
    rprint("[yellow]autoresearch dashboard: not yet implemented[/yellow]")


@app.command()
def deploy_truffle() -> None:
    """Deploy the Truffle coordinator app to your Truffle device."""
    rprint("[yellow]autoresearch deploy-truffle: not yet implemented[/yellow]")
