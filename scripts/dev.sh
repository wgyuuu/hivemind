#!/usr/bin/env bash
# Run the Bridge in the foreground for debugging (verbose logging).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
[[ -d .venv ]] && source .venv/bin/activate

export HIVEMIND_LOG_LEVEL="${HIVEMIND_LOG_LEVEL:-DEBUG}"
exec python -m hivemind
