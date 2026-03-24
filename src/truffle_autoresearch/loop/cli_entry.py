"""Entry point for running the autoresearch loop directly.

Usage:
    python -m truffle_autoresearch.loop --target-dir ./toy-lm --machine big-ron
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

app = typer.Typer(name="autoresearch-loop", no_args_is_help=True)


@app.command()
def main(
    target_dir: Path = typer.Option(..., "--target-dir", "-t", help="Path to target directory"),
    machine: str = typer.Option(..., "--machine", "-m", help="Machine name identifier"),
    max_iterations: int | None = typer.Option(None, "--max-iterations", "-n", help="Max iterations (default: infinite)"),
    skip_setup: bool = typer.Option(False, "--skip-setup", help="Skip setup (branch, prepare) for resume"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Run the autoresearch loop for a target on this machine."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from truffle_autoresearch.loop.runner import ResearchRunner

    target_path = target_dir.resolve()
    if not target_path.is_dir():
        typer.echo(f"Error: {target_path} is not a directory", err=True)
        raise typer.Exit(1)

    runner = ResearchRunner(target_dir=target_path, machine_name=machine)
    if not skip_setup:
        runner.setup()
    runner.run_loop(max_iterations=max_iterations)


if __name__ == "__main__":
    app()
