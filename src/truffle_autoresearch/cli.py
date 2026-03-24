"""CLI entry point for autoresearch."""
# deploy pipeline test

from __future__ import annotations

import os
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


# ---------------------------------------------------------------------------
# Server state helpers (lazy-loaded)
# ---------------------------------------------------------------------------
def _load_server_state() -> dict | None:
    """Load saved server state (pid, port, token) or return None."""
    import json

    from truffle_autoresearch.config.paths import SERVER_STATE_PATH

    if not SERVER_STATE_PATH.exists():
        return None
    try:
        return json.loads(SERVER_STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _server_url(state: dict) -> str:
    return f"http://localhost:{state['port']}"


def _server_headers(state: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {state['token']}"}


def _start_server_background() -> dict:
    """Start the control server as a background subprocess. Returns server state."""
    import json
    import subprocess
    import sys
    import time

    from truffle_autoresearch.config.fleet import load_fleet_config
    from truffle_autoresearch.config.paths import SERVER_STATE_PATH

    fleet = load_fleet_config()
    port = fleet.host.port

    proc = subprocess.Popen(
        [sys.executable, "-m", "truffle_autoresearch.server.run"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait for the server state file to appear (server writes it on startup)
    for _ in range(30):
        time.sleep(0.2)
        if SERVER_STATE_PATH.exists():
            try:
                state = json.loads(SERVER_STATE_PATH.read_text())
                if state.get("pid") == proc.pid:
                    return state
            except (json.JSONDecodeError, OSError):
                pass

    # Fallback — file didn't appear, but process is running
    return {"pid": proc.pid, "port": port, "token": ""}


def _kill_server(state: dict) -> bool:
    """Kill a server by PID. Returns True if killed."""
    import signal

    pid = state.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False


# ---------------------------------------------------------------------------
# Commands: run, stop, status, dashboard
# ---------------------------------------------------------------------------
@app.command()
def run(
    target: str = typer.Argument(help="Target name to run"),
    machine: Optional[str] = typer.Option(None, help="Specific machine (default: all)"),
) -> None:
    """Start the autoresearch loop on the given target."""
    import httpx

    from truffle_autoresearch.config.fleet import ConfigError, load_fleet_config
    from truffle_autoresearch.config.target import load_target_config

    # Validate fleet
    try:
        fleet = load_fleet_config()
    except ConfigError:
        rprint("[red]No fleet config found. Run 'autoresearch init' first.[/red]")
        raise typer.Exit(1)

    # Validate target
    target_dir = Path.cwd() / target
    if not target_dir.is_dir() or not (target_dir / "target.yaml").exists():
        rprint(f"[red]Target '{target}' not found in {Path.cwd()}[/red]")
        rprint("[dim]Run 'autoresearch add-target --builtin toy-lm' to create one.[/dim]")
        raise typer.Exit(1)
    target_cfg = load_target_config(target_dir)

    # Determine machines
    if machine:
        names = {m.name for m in fleet.machines}
        if machine not in names:
            rprint(f"[red]Unknown machine: {machine}. Available: {sorted(names)}[/red]")
            raise typer.Exit(1)
        machines_to_run = [machine]
    else:
        machines_to_run = [m.name for m in fleet.machines]

    # Ensure server is running
    state = _load_server_state()
    if state is None:
        rprint("[dim]Starting control server...[/dim]")
        state = _start_server_background()
        if not state.get("token"):
            rprint("[red]Failed to start control server.[/red]")
            raise typer.Exit(1)
        rprint(f"[green]Server started on port {state['port']}[/green]")

    # Start researchers
    url = _server_url(state)
    headers = _server_headers(state)
    started = 0
    for mname in machines_to_run:
        try:
            resp = httpx.post(
                f"{url}/api/researcher/{mname}/start",
                json={"target": target},
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                rprint(f"  [green]✓[/green] Started researcher on [cyan]{mname}[/cyan]")
                started += 1
            elif resp.status_code == 409:
                rprint(f"  [yellow]⚠[/yellow] Researcher already running on [cyan]{mname}[/cyan]")
            else:
                detail = resp.json().get("detail", resp.text)
                rprint(f"  [red]✗[/red] Failed on {mname}: {detail}")
        except httpx.ConnectError:
            rprint(f"  [red]✗[/red] Cannot reach server for {mname}")

    rprint()
    rprint(f"[bold]Started researchers on {started}/{len(machines_to_run)} machine(s).[/bold]")
    rprint(f"[dim]Target: {target_cfg.name} | Metric: {target_cfg.metric.name} ({target_cfg.metric.direction})[/dim]")
    rprint("[dim]Run 'autoresearch status' to check progress.[/dim]")


@app.command()
def stop(
    target: Optional[str] = typer.Argument(None, help="Target to stop (default: all)"),
    machine: Optional[str] = typer.Option(None, help="Specific machine (default: all)"),
) -> None:
    """Stop running autoresearch loops."""
    import httpx

    from truffle_autoresearch.config.fleet import ConfigError, load_fleet_config

    try:
        fleet = load_fleet_config()
    except ConfigError:
        rprint("[red]No fleet config found.[/red]")
        raise typer.Exit(1)

    state = _load_server_state()
    if state is None:
        rprint("[yellow]No server running — nothing to stop.[/yellow]")
        return

    # Determine machines
    if machine:
        machines_to_stop = [machine]
    else:
        machines_to_stop = [m.name for m in fleet.machines]

    # Stop researchers via server
    url = _server_url(state)
    headers = _server_headers(state)
    stopped = 0
    for mname in machines_to_stop:
        try:
            resp = httpx.post(
                f"{url}/api/researcher/{mname}/stop",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                rprint(f"  [green]✓[/green] Stopped researcher on [cyan]{mname}[/cyan]")
                stopped += 1
            elif resp.status_code == 404:
                rprint(f"  [dim]–[/dim] No researcher running on [cyan]{mname}[/cyan]")
            else:
                detail = resp.json().get("detail", resp.text)
                rprint(f"  [red]✗[/red] Failed on {mname}: {detail}")
        except httpx.ConnectError:
            rprint(f"  [yellow]⚠[/yellow] Cannot reach server for {mname}")

    # Kill the server itself
    if _kill_server(state):
        rprint("[dim]Server stopped.[/dim]")
    from truffle_autoresearch.config.paths import SERVER_STATE_PATH

    SERVER_STATE_PATH.unlink(missing_ok=True)

    rprint(f"\n[bold]Stopped researchers on {stopped}/{len(machines_to_stop)} machine(s).[/bold]")


@app.command()
def status() -> None:
    """Show status of all running experiments across the fleet."""
    import httpx
    from rich.console import Console
    from rich.table import Table

    from truffle_autoresearch.config.fleet import ConfigError, load_fleet_config

    console = Console()

    try:
        fleet = load_fleet_config()
    except ConfigError:
        rprint("[red]No fleet config found. Run 'autoresearch init' first.[/red]")
        raise typer.Exit(1)

    state = _load_server_state()

    # Try to get status from server
    server_data: dict | None = None
    server_reachable = False
    if state:
        try:
            health = httpx.get(f"{_server_url(state)}/api/health", timeout=3)
            server_reachable = health.status_code == 200
        except httpx.ConnectError:
            pass
        if server_reachable:
            try:
                resp = httpx.get(
                    f"{_server_url(state)}/api/status",
                    headers=_server_headers(state),
                    timeout=5,
                )
                if resp.status_code == 200:
                    server_data = resp.json()
            except httpx.ConnectError:
                pass

    # Build the table
    table = Table(title="Fleet Status", show_lines=True)
    table.add_column("Machine", style="cyan", no_wrap=True)
    table.add_column("GPU", style="green")
    table.add_column("Experiments", justify="right")
    table.add_column("Best Metric", justify="right", style="bold")
    table.add_column("Researcher", justify="center")

    for m in fleet.machines:
        gpu_label = f"{m.gpu} ({m.vram_gb}GB)"
        role = " [bold](host)[/bold]" if m.name == fleet.host.machine else ""

        if server_data and m.name in server_data.get("machines", {}):
            info = server_data["machines"][m.name]
            if "error" in info:
                table.add_row(
                    m.name + role, gpu_label, "–", "–",
                    "[red]error[/red]",
                )
            else:
                exp_count = str(info.get("experiment_count", 0))
                best = info.get("best_metric")
                best_str = f"{best:.4f}" if best is not None else "–"
                running = info.get("researcher_running", False)
                status_str = "[green]running[/green]" if running else "[dim]stopped[/dim]"
                table.add_row(m.name + role, gpu_label, exp_count, best_str, status_str)
        else:
            # Fallback — no server data for this machine
            fallback_status = "[dim]idle[/dim]" if server_reachable else "[dim]unknown[/dim]"
            table.add_row(
                m.name + role, gpu_label, "–", "–",
                fallback_status,
            )

    console.print(table)

    if not state or not server_reachable:
        rprint("\n[dim]Server not running. Start with 'autoresearch run <target>' or 'autoresearch dashboard'.[/dim]")


@app.command()
def dashboard() -> None:
    """Launch the web dashboard (FastAPI server + static frontend)."""
    from truffle_autoresearch.config.fleet import ConfigError, load_fleet_config

    try:
        fleet = load_fleet_config()
    except ConfigError:
        rprint("[red]No fleet config found. Run 'autoresearch init' first.[/red]")
        raise typer.Exit(1)

    port = fleet.host.port
    rprint(f"[bold]Starting AutoResearch Dashboard on http://localhost:{port}[/bold]")
    rprint("[dim]Press Ctrl+C to stop.[/dim]\n")

    from truffle_autoresearch.server.run import start_server

    start_server(port=port)


@app.command()
def deploy_truffle() -> None:
    """Deploy the Truffle coordinator app to your Truffle device."""
    rprint("[yellow]autoresearch deploy-truffle: not yet implemented[/yellow]")
