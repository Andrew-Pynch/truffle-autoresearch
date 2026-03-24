"""Results log management for autoresearch targets."""

from __future__ import annotations

from pathlib import Path


class ResultsLog:
    """Manages results.tsv for a target."""

    HEADER = "experiment_number\tcommit\tmetric_value\tvram_gb\tstatus\tdescription"

    def __init__(self, target_dir: Path) -> None:
        self.path = target_dir / "results.tsv"

    def initialize(self) -> None:
        """Create results.tsv with header if it doesn't exist."""
        if not self.path.exists():
            self.path.write_text(self.HEADER + "\n")

    def append(
        self,
        commit: str,
        metric_value: float | None,
        status: str,
        description: str,
        vram_gb: str = "",
    ) -> None:
        """Append a result row. Auto-increments experiment_number."""
        num = self.count() + 1
        val = f"{metric_value:.6f}" if metric_value is not None else "0.000000"
        line = f"{num}\t{commit}\t{val}\t{vram_gb}\t{status}\t{description}\n"
        with open(self.path, "a") as f:
            f.write(line)

    def get_best(self, direction: str) -> float | None:
        """Return the best metric value so far, respecting direction."""
        values: list[float] = []
        for row in self._data_rows():
            parts = row.split("\t")
            if len(parts) < 5:
                continue
            status = parts[4].strip()
            if status == "crash":
                continue
            try:
                val = float(parts[2])
            except (ValueError, IndexError):
                continue
            if val == 0.0:
                continue
            values.append(val)
        if not values:
            return None
        return min(values) if direction == "minimize" else max(values)

    def read_all(self) -> str:
        """Return full contents of results.tsv as string."""
        if self.path.exists():
            return self.path.read_text()
        return ""

    def count(self) -> int:
        """Return number of experiments (non-header lines)."""
        return len(self._data_rows())

    def _data_rows(self) -> list[str]:
        """Return non-header, non-empty lines."""
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()
        # Skip header (first line) and empty lines
        return [line for line in lines[1:] if line.strip()]
