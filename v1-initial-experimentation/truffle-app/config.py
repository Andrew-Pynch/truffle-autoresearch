"""Configuration for the AutoResearch Coordinator."""

import logging
import os

logger = logging.getLogger(__name__)

CONTROL_SERVER_URL = os.environ.get("CONTROL_SERVER_URL", "http://localhost:8420")
CONTROL_SERVER_TOKEN = os.environ.get("CONTROL_SERVER_TOKEN", "")

MACHINES = {
    "4090": {
        "name": "4090",
        "display_name": "big-ron",
        "gpu": "RTX 4090",
        "vram": "24GB",
    },
    "3080": {
        "name": "3080",
        "display_name": "big-bertha",
        "gpu": "RTX 3080",
        "vram": "10GB",
    },
}


def get_machines() -> dict[str, dict]:
    """Return dict of machine configs keyed by machine name."""
    return MACHINES


STATE_FILE_PATH = os.environ.get(
    "COORDINATOR_STATE_PATH",
    "/tmp/autoresearch_coordinator_state.json",
)
