"""Autoresearch loop orchestration.

Replaces v1's autoresearch_loop.sh with a Python implementation
that spawns Claude agent sessions, manages git branches,
syncs results, and handles restarts.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from truffle_autoresearch.config.target import TargetConfig, load_target_config
from truffle_autoresearch.loop.git import GitManager
from truffle_autoresearch.loop.results import ResultsLog

logger = logging.getLogger(__name__)

SESSION_TIMEOUT = 7200  # 2 hours max per claude session (safety net, from v1)
INTER_ITERATION_SLEEP = 10  # seconds between iterations (from v1)


class ResearchRunner:
    """Orchestrates autonomous research on a single machine for a single target."""

    def __init__(self, target_dir: Path, machine_name: str) -> None:
        """
        Args:
            target_dir: Path to the target directory (contains target.yaml, train.py, etc.)
            machine_name: Identifier for this machine (used in branch names, results.tsv).
        """
        self.target_dir = target_dir.resolve()
        self.machine_name = machine_name
        self.config: TargetConfig = load_target_config(self.target_dir)
        self.git = GitManager(self.target_dir)
        self.results = ResultsLog(self.target_dir)
        self.iteration = 0
        self._log_dir = self.target_dir / "logs"

    def setup(self) -> None:
        """One-time setup: prepare command, git branch, results.tsv."""
        self._log_dir.mkdir(exist_ok=True)

        # Run prepare command if defined (e.g., data download)
        if self.config.prepare_command:
            logger.info("Running prepare command: %s", self.config.prepare_command)
            subprocess.run(
                self.config.prepare_command,
                shell=True,
                cwd=self.target_dir,
                check=True,
            )

        # Create git branch: autoresearch/{machine_name}-{date}
        date_str = datetime.now().strftime("%b%d").lower()
        branch = f"autoresearch/{self.machine_name}-{date_str}"
        self.git.create_branch(branch)

        # Initialize results.tsv
        self.results.initialize()

    def run_loop(self, max_iterations: int | None = None) -> None:
        """Main loop. Runs until interrupted or max_iterations reached.

        Each iteration spawns a fresh Claude Code session, syncs results,
        then sleeps before the next iteration.
        """
        logger.info(
            "Starting autoresearch loop: target=%s machine=%s",
            self.config.name,
            self.machine_name,
        )
        try:
            while max_iterations is None or self.iteration < max_iterations:
                self.iteration += 1
                self._print_banner()

                try:
                    self._run_iteration()
                except Exception:
                    logger.exception("Iteration %d failed", self.iteration)

                try:
                    self._sync_results()
                except Exception:
                    logger.exception("Results sync failed after iteration %d", self.iteration)

                if max_iterations is None or self.iteration < max_iterations:
                    logger.info("Sleeping %ds before next iteration...", INTER_ITERATION_SLEEP)
                    time.sleep(INTER_ITERATION_SLEEP)

        except KeyboardInterrupt:
            logger.info("Interrupted — exiting autoresearch loop after %d iterations", self.iteration)

    def _print_banner(self) -> None:
        """Print iteration banner to stdout."""
        banner = (
            f"\n{'=' * 42}\n"
            f"AUTORESEARCH ITERATION {self.iteration}\n"
            f"Machine: {self.machine_name}\n"
            f"Target: {self.config.name}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'=' * 42}"
        )
        print(banner, flush=True)

    def _run_iteration(self) -> None:
        """Run a single Claude Code agent session."""
        # Pre-iteration cleanup: revert dirty state from crashed previous session
        if self.git.has_uncommitted_changes(self.config.mutable_file):
            logger.warning("Dirty state detected, reverting %s", self.config.mutable_file)
            self.git.revert_mutable_file(self.config.mutable_file)

        prompt = self._build_agent_prompt()

        # Build clean environment — unset ANTHROPIC_API_KEY (critical safety from v1)
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        cmd = [
            "claude",
            "-p",
            "--dangerously-skip-permissions",
            "--model",
            self.config.agent.model,
            prompt,
        ]

        log_path = self._log_dir / f"iteration-{self.iteration}.log"
        logger.info("Spawning agent session (log: %s)", log_path)

        try:
            with open(log_path, "w") as log_f:
                result = subprocess.run(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    cwd=self.target_dir,
                    env=env,
                    timeout=SESSION_TIMEOUT,
                )
            logger.info("Agent exited with code %d", result.returncode)
        except subprocess.TimeoutExpired:
            logger.warning("Agent session timed out after %ds", SESSION_TIMEOUT)
        except Exception:
            logger.exception("Agent session failed")

    def _build_agent_prompt(self) -> str:
        """Build the prompt passed to claude -p.

        The prompt is target-agnostic — all specifics come from TargetConfig.
        """
        cfg = self.config
        metric = cfg.metric

        direction_word = "lower" if metric.direction == "minimize" else "higher"
        best = self.results.get_best(metric.direction)
        best_str = f"{best:.6f}" if best is not None else "no baseline yet"
        count = self.results.count()
        minutes = cfg.time_budget_seconds // 60

        return f"""\
You are an autonomous autoresearch agent. Your job is to improve the {metric.name} metric by modifying {cfg.mutable_file}.

CRITICAL INSTRUCTIONS:
1. Read {cfg.agent.system_prompt_file} for the full research protocol
2. Read results.tsv to see what has already been tried — DO NOT repeat failed experiments
3. Read {cfg.mutable_file} to see the current state (it reflects the best configuration so far)
4. Pick a NEW modification that hasn't been tried
5. Edit {cfg.mutable_file} with your change
6. Run: {cfg.run_command}
7. Wait for the run to complete (~{minutes} minutes)
8. Check {metric.source} for the final {metric.name} value
9. Record the result in results.tsv (tab-separated, append a new line):
   experiment_number\tcommit\tmetric_value\tvram_gb\tstatus\tdescription
10. If {metric.name} IMPROVED ({direction_word} is better): keep the change (git add {cfg.mutable_file}, git commit with descriptive message)
11. If {metric.name} DID NOT IMPROVE: revert (git checkout {cfg.mutable_file})
12. Repeat from step 4 — do as many experiments as you can

CURRENT STATE:
- Experiments completed: {count}
- Best {metric.name} so far: {best_str}
- Metric direction: {metric.direction} ({direction_word} is better)

RULES:
- ONLY edit {cfg.mutable_file}. Do NOT modify any other files.
- Do NOT delete or corrupt results.tsv.
- ALWAYS use '{cfg.run_command}' to run experiments.
- ALWAYS wait for the run to fully complete before checking results.
- Do NOT stop to ask the user anything. You are fully autonomous. Keep going until you run out of ideas or context."""

    def _extract_metric(self) -> float | None:
        """Extract the metric from the configured source file.

        Reads config.metric.source and applies config.metric.pattern regex.
        Returns the float value, or None if not found.
        """
        source_path = self.target_dir / self.config.metric.source
        if not source_path.exists():
            return None
        content = source_path.read_text()
        match = re.search(self.config.metric.pattern, content)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                return None
        return None

    def _sync_results(self) -> None:
        """Sync results to git remote."""
        try:
            self.git.sync_results(self.machine_name)
        except Exception:
            logger.exception("Sync failed, continuing")
