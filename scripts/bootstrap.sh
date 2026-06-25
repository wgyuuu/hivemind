#!/usr/bin/env bash
# Create a virtualenv, install Hivemind (editable) + deps, then run doctor.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
VENV="$ROOT/.venv"

echo "==> Creating venv at $VENV"
"$PY" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> Upgrading pip"
python -m pip install --upgrade pip

echo "==> Installing hivemind (editable, with dev extras)"
python -m pip install -e ".[dev]"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "==> Creating .env from template (fill in your DingTalk credentials!)"
  cp "$ROOT/.env.example" "$ROOT/.env"
fi

echo "==> Running doctor"
"$ROOT/scripts/doctor.sh" || true

echo "==> Done. Activate with: source .venv/bin/activate"
