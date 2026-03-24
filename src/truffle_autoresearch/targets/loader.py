"""Target discovery and validation.

Finds target directories in builtin and user paths,
validates each has a valid target.yaml.
"""

from __future__ import annotations

from pathlib import Path

from truffle_autoresearch.config.fleet import ConfigError
from truffle_autoresearch.config.target import TargetConfig


def find_targets() -> list[tuple[Path, TargetConfig]]:
    """Discover all available targets (builtin + user).

    Searches BUILTIN_TARGETS_DIR and USER_TARGETS_DIR for directories
    containing a valid target.yaml.

    Returns:
        List of (directory, validated_config) tuples.
    """
    raise NotImplementedError


def get_target(name: str) -> tuple[Path, TargetConfig]:
    """Get a specific target by name.

    Args:
        name: Target name (e.g., 'toy-lm').

    Returns:
        Tuple of (directory, validated_config).

    Raises:
        ConfigError: If target not found.
    """
    raise NotImplementedError
