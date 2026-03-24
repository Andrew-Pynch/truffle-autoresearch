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
    rprint("[yellow]autoresearch init: not yet implemented[/yellow]")


@app.command()
def add_machine(
    name: str = typer.Argument(help="Machine name (e.g., 'big-ron')"),
    tailscale_ip: str = typer.Option(..., help="Tailscale IP address"),
    ssh_user: str = typer.Option(..., help="SSH username"),
    gpu: str = typer.Option(..., help="GPU model (e.g., 'RTX 4090')"),
    vram_gb: int = typer.Option(..., help="GPU VRAM in GB"),
) -> None:
    """Add a machine to the fleet configuration."""
    rprint("[yellow]autoresearch add-machine: not yet implemented[/yellow]")


@app.command()
def remove_machine(
    name: str = typer.Argument(help="Machine name to remove"),
) -> None:
    """Remove a machine from the fleet configuration."""
    rprint("[yellow]autoresearch remove-machine: not yet implemented[/yellow]")


@app.command()
def add_target(
    name: str = typer.Argument(help="Target name"),
    directory: Optional[Path] = typer.Option(None, help="Path to target directory"),
    builtin: Optional[str] = typer.Option(None, "--builtin", help="Use a builtin target (e.g., 'toy-lm')"),
) -> None:
    """Add a research target. Use --builtin to copy a shipped target."""
    rprint("[yellow]autoresearch add-target: not yet implemented[/yellow]")


@app.command()
def list_targets() -> None:
    """List all available targets (builtin and user-configured)."""
    rprint("[yellow]autoresearch list-targets: not yet implemented[/yellow]")


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
