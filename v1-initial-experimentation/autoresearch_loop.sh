#!/bin/bash
unset ANTHROPIC_API_KEY
set -euo pipefail

MACHINE_ID="${1:?Usage: autoresearch_loop.sh <machine-id>}"
REPO_DIR="$HOME/personal/truffle-autoresearch"
AUTORESEARCH_DIR="$REPO_DIR/autoresearch"
MODEL="${MODEL:-opus}"
ITERATION=0
SESSION_TIMEOUT=7200  # 2 hours max per claude session (safety net)

# Auto-create git branch if needed
cd "$AUTORESEARCH_DIR"
BRANCH="autoresearch/${MACHINE_ID}-$(date +%b%d | tr '[:upper:]' '[:lower:]')"
if ! git rev-parse --verify "$BRANCH" &>/dev/null; then
    echo "Creating branch $BRANCH"
    git checkout -b "$BRANCH"
else
    echo "Checking out existing branch $BRANCH"
    git checkout "$BRANCH"
fi

while true; do
    ITERATION=$((ITERATION + 1))
    echo "=========================================="
    echo "AUTORESEARCH ITERATION $ITERATION"
    echo "Machine: $MACHINE_ID"
    echo "Time: $(date)"
    echo "=========================================="

    cd "$AUTORESEARCH_DIR"

    # Use timeout as safety net; || true so set -e doesn't kill the loop
    timeout ${SESSION_TIMEOUT} claude -p \
        --dangerously-skip-permissions \
        --model "$MODEL" \
        "You are an autonomous autoresearch agent. Your job is to improve a small language model's val_bpb score by modifying train.py hyperparameters.

CRITICAL INSTRUCTIONS:
1. Read program.md for the full autoresearch protocol
2. Read results.tsv to see what has already been tried — DO NOT repeat failed experiments
3. Read train.py to see the current state (it reflects the best configuration so far)
4. Pick a NEW hyperparameter modification that hasn't been tried
5. Edit train.py with your change
6. Run: uv run train.py
7. Wait for training to complete (~5 minutes)
8. Check run.log for the final val_bpb score
9. Record the result in results.tsv following the exact format in program.md
10. If val_bpb IMPROVED: keep the change (git add, git commit with descriptive message)
11. If val_bpb DID NOT IMPROVE: revert train.py to previous state (git checkout train.py)
12. Repeat from step 4 — do as many experiments as you can

STRATEGY GUIDANCE:
- Every 'make it bigger' attempt has failed because fewer training steps fit in 5 minutes
- Focus on subtle hyperparameter tuning: learning rates, warmdown ratios, weight decay, etc.
- Check results.tsv carefully — many obvious things have been tried already
- The current best configs were found through LR tuning, not architecture changes
- Think creatively: curriculum learning, loss function tweaks, initialization schemes, etc.

DO NOT modify prepare.py or the evaluation infrastructure.
DO NOT delete or corrupt results.tsv.
ALWAYS use 'uv run train.py' to run training (not python train.py).
ALWAYS wait for training to fully complete before checking results." \
        2>&1 | tee "/tmp/autoresearch-${MACHINE_ID}-iter${ITERATION}.log" || true

    EXIT_CODE=$?
    echo ""
    echo "Agent exited with code $EXIT_CODE at $(date)"

    # Sync results to GitHub
    echo "Syncing results..."
    cd "$REPO_DIR"
    bash sync_results.sh "$MACHINE_ID" || echo "Sync failed, continuing..."

    echo "Sleeping 10s before next iteration..."
    sleep 10
done
