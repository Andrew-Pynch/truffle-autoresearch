"""Fleet configuration schema and loader."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from truffle_autoresearch.config.paths import FLEET_CONFIG_PATH


class ConfigError(Exception):
    """Raised when fleet or target configuration is invalid or missing."""


class MachineConfig(BaseModel):
    """A single machine in the fleet."""

    model_config = ConfigDict(frozen=True)

    name: str
    tailscale_ip: str
    ssh_user: str
    gpu: str
    vram_gb: Annotated[int, Field(gt=0)]

    @field_validator("tailscale_ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        """Validate that tailscale_ip is a valid IP address."""
        try:
            ipaddress.ip_address(v)
        except ValueError as e:
            raise ValueError(f"Invalid IP address: {v}") from e
        return v


class HostConfig(BaseModel):
    """Which machine hosts the control server."""

    model_config = ConfigDict(frozen=True)

    machine: str
    ngrok_authtoken: str = ""
    port: int = 8420


class TruffleConfig(BaseModel):
    """Truffle device integration settings."""

    model_config = ConfigDict(frozen=True)

    device_id: str
    enabled: bool = True


class FleetConfig(BaseModel):
    """Top-level fleet.yaml schema.

    Example fleet.yaml:
        version: 1
        host:
          machine: big-bertha
          port: 8420
        machines:
          - name: big-ron
            tailscale_ip: 100.82.30.45
            ssh_user: andrew
            gpu: RTX 4090
            vram_gb: 24
        truffle:
          device_id: truffle-7197
          enabled: true
    """

    version: int = 1
    host: HostConfig
    machines: list[MachineConfig]
    truffle: TruffleConfig | None = None

    @model_validator(mode="after")
    def host_machine_exists(self) -> FleetConfig:
        """Ensure host.machine references a machine in the fleet."""
        machine_names = {m.name for m in self.machines}
        if self.host.machine not in machine_names:
            raise ValueError(
                f"host.machine '{self.host.machine}' not found in machines list. "
                f"Available: {sorted(machine_names)}"
            )
        return self


def load_fleet_config(path: Path | None = None) -> FleetConfig:
    """Load and validate fleet.yaml.

    Args:
        path: Override path to fleet.yaml. Defaults to ~/.autoresearch/fleet.yaml.

    Returns:
        Validated FleetConfig.

    Raises:
        ConfigError: If the file is missing, unreadable, or invalid.
    """
    config_path = path or FLEET_CONFIG_PATH
    if not config_path.exists():
        raise ConfigError(
            f"Fleet config not found at {config_path}\n"
            f"Run 'autoresearch init' to create one."
        )
    try:
        raw = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {config_path}: {e}") from e
    if raw is None:
        raise ConfigError(f"Fleet config is empty: {config_path}")
    try:
        return FleetConfig.model_validate(raw)
    except Exception as e:
        raise ConfigError(f"Fleet config validation failed: {e}") from e
