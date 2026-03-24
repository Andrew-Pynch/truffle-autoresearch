# toy-lm autoresearch

## Target Contract

This experiment is managed by autoresearch. The rules are defined in `target.yaml`:

- **Mutable file**: `train.py` — this is the ONLY file you may edit.
- **Run command**: `uv run train.py` — output is captured to `run.log`.
- **Metric**: `val_bpb`, extracted from `run.log`. Lower is better.
- **Time budget**: 300 seconds (5 minutes wall-clock training time, excluding startup/eval overhead).
- **Prepare command**: `uv run prepare.py` — downloads data and trains the tokenizer. Run once before experimenting.

The autoresearch orchestrator handles git branching, result logging, and keep/discard decisions. Your job is to propose and implement changes to `train.py`.

## Context

Read these files for full context before starting:

- `prepare.py` — fixed constants, data prep, tokenizer, dataloader, evaluation. **Do not modify.**
- `train.py` — the file you modify. Model architecture, optimizer, training loop.

Each experiment runs on a single GPU. The training script runs for a **fixed time budget of 5 minutes** (wall clock training time, excluding startup/compilation). It is launched as: `uv run train.py`.

## Rules

**What you CAN do:**
- Modify `train.py` — this is the only file you edit. Everything is fair game: model architecture, optimizer, hyperparameters, training loop, batch size, model size, etc.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only. It contains the fixed evaluation, data loading, tokenizer, and training constants (time budget, sequence length, etc).
- Install new packages or add dependencies. You can only use what's already in `pyproject.toml`.
- Modify the evaluation harness. The `evaluate_bpb` function in `prepare.py` is the ground truth metric.

## The Goal

**Get the lowest val_bpb.** Since the time budget is fixed, you don't need to worry about training time — it's always 5 minutes. Everything is fair game: change the architecture, the optimizer, the hyperparameters, the batch size, the model size. The only constraint is that the code runs without crashing and finishes within the time budget.

**VRAM** is a soft constraint. Some increase is acceptable for meaningful val_bpb gains, but it should not blow up dramatically.

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Conversely, removing something and getting equal or better results is a great outcome — that's a simplification win. When evaluating whether to keep a change, weigh the complexity cost against the improvement magnitude. A 0.001 val_bpb improvement that adds 20 lines of hacky code? Probably not worth it. A 0.001 val_bpb improvement from deleting code? Definitely keep. An improvement of ~0 but much simpler code? Keep.

## Output Format

Once the script finishes it prints a summary like this:

```
---
val_bpb:          0.997900
training_seconds: 300.1
total_seconds:    325.9
peak_vram_mb:     45060.2
mfu_percent:      39.80
total_tokens_M:   499.6
num_steps:        953
num_params_M:     50.3
depth:            8
```

You can extract the key metric: `grep "^val_bpb:" run.log`

## Experiment Loop

1. Read `train.py` for full context on the current state of the code.
2. Form a hypothesis — what change might lower val_bpb?
3. Edit `train.py` to implement the change.
4. The orchestrator runs the experiment: `uv run train.py > run.log 2>&1`
5. Check results. If val_bpb improved (lower), the change is kept. If not, it's reverted.
6. Repeat from step 1.

**The first run** should always establish the baseline — run the training script as-is.

**Crashes**: If a run crashes (OOM, bug, etc.), use your judgment: if it's something simple to fix (typo, missing import), fix it and re-run. If the idea itself is fundamentally broken, move on.

## NEVER STOP

Once the experiment loop has begun, do NOT pause to ask the user if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The user might be asleep, or away from the computer and expects you to continue working *indefinitely* until you are manually stopped. You are autonomous. If you run out of ideas, think harder — re-read the code for new angles, try combining previous near-misses, try more radical architectural changes. The loop runs until the user interrupts you, period.

As a reference: each experiment takes ~5 minutes, so you can run ~12/hour, ~100 overnight. The user wakes up to experimental results, all completed by you while they slept.
