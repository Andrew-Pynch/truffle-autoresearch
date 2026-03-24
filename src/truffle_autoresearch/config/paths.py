"""Filesystem paths and constants for autoresearch."""

from __future__ import annotations

import os
from pathlib import Path

# Root config directory (override with AUTORESEARCH_HOME for testing)
AUTORESEARCH_DIR: Path = Path(
    os.environ.get("AUTORESEARCH_HOME", Path.home() / ".autoresearch")
)

# Fleet configuration
FLEET_CONFIG_PATH: Path = AUTORESEARCH_DIR / "fleet.yaml"

# Builtin targets shipped with the package
BUILTIN_TARGETS_DIR: Path = Path(__file__).resolve().parent.parent / "targets" / "builtin"

# User targets directory
USER_TARGETS_DIR: Path = AUTORESEARCH_DIR / "targets"

# Default server port (from v1's :8420)
DEFAULT_SERVER_PORT: int = 8420

# Default time budget in seconds (from v1's 5-minute training budget)
DEFAULT_TIME_BUDGET_SECONDS: int = 300
