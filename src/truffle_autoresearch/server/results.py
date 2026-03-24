"""Results TSV parsing and trajectory annotation."""

from __future__ import annotations

import csv
import io
from typing import Any


def parse_results_tsv(content: str) -> list[dict[str, Any]]:
    """Parse a results.tsv file into structured data.

    Uses csv.DictReader with tab delimiter. Values that look like floats
    are automatically converted; everything else stays as a string.

    Returns:
        List of row dicts. Empty list if content is empty or has no data rows.
    """
    content = content.strip()
    if not content:
        return []

    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")
    for row in reader:
        parsed: dict[str, Any] = {}
        for key, value in row.items():
            if value is None:
                parsed[key] = value
                continue
            try:
                parsed[key] = float(value)
            except (ValueError, TypeError):
                parsed[key] = value
        rows.append(parsed)
    return rows


def annotate_trajectory(
    results: list[dict[str, Any]], metric_name: str, direction: str
) -> list[dict[str, Any]]:
    """Add experiment_number and is_new_best fields to each result.

    Args:
        results: Parsed results from parse_results_tsv.
        metric_name: Column name for the metric (e.g. "val_bpb").
        direction: "minimize" or "maximize".

    Returns:
        New list with experiment_number (1-indexed) and is_new_best (bool) added.
    """
    annotated: list[dict[str, Any]] = []
    best_so_far: float | None = None

    for i, row in enumerate(results, 1):
        is_new_best = False
        metric_val = row.get(metric_name)

        if row.get("status") == "keep" and isinstance(metric_val, float):
            if best_so_far is None:
                is_new_best = True
                best_so_far = metric_val
            elif direction == "minimize" and metric_val < best_so_far:
                is_new_best = True
                best_so_far = metric_val
            elif direction == "maximize" and metric_val > best_so_far:
                is_new_best = True
                best_so_far = metric_val

        annotated.append({
            **row,
            "experiment_number": i,
            "is_new_best": is_new_best,
        })

    return annotated
