"""Target discovery and validation.

Finds target directories in the current working directory and
locates builtin targets shipped with the package.
"""

from __future__ import annotations

import importlib.resources
import logging
import shutil
from pathlib import Path

from truffle_autoresearch.config.fleet import ConfigError
from truffle_autoresearch.config.target import TargetConfig, load_target_config

logger = logging.getLogger(__name__)


def _builtin_dir() -> Path:
    """Return the on-disk path to the builtin targets package directory."""
    ref = importlib.resources.files("truffle_autoresearch.targets.builtin")
    return Path(str(ref))


def list_builtin_targets() -> list[str]:
    """Return sorted names of builtin targets.

    Scans the package's builtin/ directory for subdirectories that
    contain a target.yaml. Directories starting with '_' (like _skeleton)
    are excluded.
    """
    builtin = _builtin_dir()
    if not builtin.is_dir():
        return []
    return sorted(
        d.name
        for d in builtin.iterdir()
        if d.is_dir()
        and not d.name.startswith("_")
        and (d / "target.yaml").exists()
    )


def copy_builtin_target(name: str, destination: Path) -> None:
    """Copy a builtin target to the destination directory.

    Args:
        name: Builtin target name (e.g., 'toy-lm' or '_skeleton').
        destination: Where to copy the target. Must not already exist.

    Raises:
        ConfigError: If the builtin target doesn't exist or destination exists.
    """
    source = _builtin_dir() / name
    if not source.is_dir() or not (source / "target.yaml").exists():
        available = list_builtin_targets()
        raise ConfigError(
            f"No builtin target named '{name}'. Available: {available}"
        )
    if destination.exists():
        raise ConfigError(f"Destination already exists: {destination}")
    shutil.copytree(source, destination)


def find_targets() -> list[tuple[Path, TargetConfig]]:
    """Discover targets in current working directory.

    Scans subdirectories of cwd for directories containing a valid
    target.yaml. Invalid targets are skipped with a warning.

    Returns:
        List of (directory, validated_config) tuples, sorted by name.
    """
    results = []
    cwd = Path.cwd()
    for child in sorted(cwd.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "target.yaml").exists():
            continue
        try:
            config = load_target_config(child)
            results.append((child, config))
        except ConfigError as e:
            logger.warning("Skipping %s: %s", child.name, e)
    return results


def get_target(name: str) -> tuple[Path, TargetConfig]:
    """Get a specific target by name from the current working directory.

    Args:
        name: Target name (e.g., 'toy-lm'). Looked up as a subdirectory of cwd.

    Returns:
        Tuple of (directory, validated_config).

    Raises:
        ConfigError: If target not found or invalid.
    """
    target_dir = Path.cwd() / name
    if not target_dir.is_dir():
        raise ConfigError(f"Target directory not found: {target_dir}")
    return (target_dir, load_target_config(target_dir))
