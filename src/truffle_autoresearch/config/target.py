"""Target configuration schema and loader."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from truffle_autoresearch.config.fleet import ConfigError
from truffle_autoresearch.config.paths import DEFAULT_TIME_BUDGET_SECONDS


class MetricConfig(BaseModel):
    """How to extract and interpret the optimization metric."""

    model_config = ConfigDict(frozen=True)

    name: str
    source: str
    pattern: str
    direction: Literal["minimize", "maximize"]

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """Ensure the pattern compiles and has exactly one capture group."""
        try:
            compiled = re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e
        if compiled.groups != 1:
            raise ValueError(
                f"Metric pattern must have exactly 1 capture group, "
                f"got {compiled.groups}: {v}"
            )
        return v


class AgentConfig(BaseModel):
    """Agent configuration for the research loop."""

    model_config = ConfigDict(frozen=True)

    model: str = "opus"
    system_prompt_file: str = "program.md"


class TargetConfig(BaseModel):
    """Top-level target.yaml schema.

    Example target.yaml:
        name: toy-lm
        description: "Karpathy's toy language model autoresearch"
        mutable_file: train.py
        run_command: "uv run train.py"
        prepare_command: "uv run prepare.py"
        metric:
          name: val_bpb
          source: run.log
          pattern: "val_bpb (\\d+\\.\\d+)"
          direction: minimize
        time_budget_seconds: 300
        agent:
          model: opus
          system_prompt_file: program.md
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""
    mutable_file: str
    run_command: str
    prepare_command: str | None = None
    metric: MetricConfig
    time_budget_seconds: int = Field(default=DEFAULT_TIME_BUDGET_SECONDS, gt=0)
    agent: AgentConfig = Field(default_factory=AgentConfig)


def load_target_config(directory: Path) -> TargetConfig:
    """Load and validate target.yaml from the given directory.

    Args:
        directory: Path to a target directory containing target.yaml.

    Returns:
        Validated TargetConfig.

    Raises:
        ConfigError: If the file is missing, unreadable, or invalid.
    """
    target_file = directory / "target.yaml"
    if not target_file.exists():
        raise ConfigError(
            f"No target.yaml found in {directory}\n"
            f"A target directory must contain a target.yaml file."
        )
    try:
        raw = yaml.safe_load(target_file.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {target_file}: {e}") from e
    if raw is None:
        raise ConfigError(f"target.yaml is empty: {target_file}")
    try:
        config = TargetConfig.model_validate(raw)
    except Exception as e:
        raise ConfigError(f"Target config validation failed in {directory}: {e}") from e

    # Verify referenced files exist in the target directory
    mutable_path = directory / config.mutable_file
    if not mutable_path.exists():
        raise ConfigError(
            f"mutable_file '{config.mutable_file}' not found in {directory}"
        )

    prompt_path = directory / config.agent.system_prompt_file
    if not prompt_path.exists():
        raise ConfigError(
            f"system_prompt_file '{config.agent.system_prompt_file}' not found in {directory}"
        )

    return config
