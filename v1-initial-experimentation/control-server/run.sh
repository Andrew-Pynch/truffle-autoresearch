#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Load env vars from repo root .env if it exists
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
fi

exec uvicorn server:app --host 0.0.0.0 --port 8420
