#!/usr/bin/env bash
set -euo pipefail
MACHINE="${1:?Usage: ./sync_results.sh <machine-id> (e.g., 4090, 3080, orin)}"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
SOURCE="${REPO_ROOT}/autoresearch/results.tsv"
DEST="${REPO_ROOT}/results/${MACHINE}-results.tsv"
[[ -f "$SOURCE" ]] || { echo "ERROR: $SOURCE not found"; exit 1; }
cp "$SOURCE" "$DEST"
cd "$REPO_ROOT"
git add "results/${MACHINE}-results.tsv"
git commit -m "update ${MACHINE} results"
git push origin main
