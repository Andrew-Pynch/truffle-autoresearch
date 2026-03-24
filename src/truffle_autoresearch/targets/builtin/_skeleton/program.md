# Research Target

## Target Contract

This experiment is managed by autoresearch. The rules are defined in `target.yaml`:

- **Mutable file**: `train.py` — the ONLY file you may edit.
- **Run command**: output is captured to `run.log`.
- **Metric**: extracted from `run.log` using the pattern in `target.yaml`.
- **Goal**: see `target.yaml` for direction (minimize or maximize).
- **Time budget**: see `target.yaml` for the wall-clock training budget.

The autoresearch orchestrator handles git branching, result logging, and keep/discard decisions. Your job is to propose and implement changes to the mutable file.

## Rules

- Only modify the mutable file specified in `target.yaml`.
- Do not install new packages or modify dependencies.
- Do not modify the evaluation metric or data pipeline.

## Experiment Loop

1. Read the mutable file for full context.
2. Form a hypothesis — what change might improve the metric?
3. Edit the mutable file to implement the change.
4. The orchestrator runs the experiment and captures output to `run.log`.
5. Check results: if improved, keep. If not, revert.
6. Repeat.

The first run should always establish a baseline — run the code as-is.

If a run crashes, use your judgment: fix simple bugs and re-run, or move on if the idea is broken.

## NEVER STOP

Once the experiment loop begins, do NOT pause to ask the user if you should continue. You are autonomous. If you run out of ideas, think harder — re-read the code, try combining past near-misses, try more radical changes. The loop runs until manually interrupted.
