"""Git operations for the autoresearch loop."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GitManager:
    """Handles git operations for the autoresearch loop."""

    def __init__(self, target_dir: Path) -> None:
        self.target_dir = target_dir

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run a git command in the target directory."""
        return subprocess.run(
            ["git", *args],
            cwd=self.target_dir,
            capture_output=True,
            text=True,
        )

    def create_branch(self, branch_name: str) -> None:
        """Create and checkout a new branch. If it exists, just check it out."""
        check = self._run("rev-parse", "--verify", branch_name)
        if check.returncode == 0:
            logger.info("Checking out existing branch %s", branch_name)
            result = self._run("checkout", branch_name)
        else:
            logger.info("Creating branch %s", branch_name)
            result = self._run("checkout", "-b", branch_name)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to checkout branch {branch_name}: {result.stderr.strip()}"
            )

    def get_current_commit(self) -> str:
        """Return short hash of HEAD."""
        result = self._run("rev-parse", "--short=7", "HEAD")
        if result.returncode != 0:
            raise RuntimeError(f"Failed to get current commit: {result.stderr.strip()}")
        return result.stdout.strip()

    def get_mutable_file_hash(self, mutable_file: str) -> str:
        """Return git hash of the mutable file (to detect changes)."""
        result = self._run("hash-object", mutable_file)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to hash {mutable_file}: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def commit_change(self, mutable_file: str, message: str) -> str:
        """Stage and commit the mutable file. Return new commit hash."""
        add_result = self._run("add", mutable_file)
        if add_result.returncode != 0:
            raise RuntimeError(f"git add failed: {add_result.stderr.strip()}")
        commit_result = self._run("commit", "-m", message)
        if commit_result.returncode != 0:
            raise RuntimeError(f"git commit failed: {commit_result.stderr.strip()}")
        return self.get_current_commit()

    def revert_mutable_file(self, mutable_file: str) -> None:
        """Revert the mutable file to the last committed version."""
        result = self._run("checkout", "--", mutable_file)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to revert {mutable_file}: {result.stderr.strip()}"
            )

    def has_uncommitted_changes(self, mutable_file: str) -> bool:
        """Check if the mutable file has uncommitted changes."""
        result = self._run("diff", "--name-only", mutable_file)
        return bool(result.stdout.strip())

    def sync_results(self, machine_name: str) -> None:
        """Commit and push results.tsv. Failures are logged, not raised."""
        try:
            add = self._run("add", "results.tsv")
            if add.returncode != 0:
                logger.warning("git add results.tsv failed: %s", add.stderr.strip())
                return

            # Check if there's anything to commit
            diff = self._run("diff", "--cached", "--name-only")
            if not diff.stdout.strip():
                logger.info("No results changes to sync")
                return

            commit = self._run("commit", "-m", f"update {machine_name} results")
            if commit.returncode != 0:
                logger.warning("git commit failed: %s", commit.stderr.strip())
                return

            push = self._run("push", "origin", "HEAD")
            if push.returncode != 0:
                logger.warning("git push failed: %s", push.stderr.strip())
        except Exception as e:
            logger.warning("Sync failed, continuing: %s", e)
