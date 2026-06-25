#!/usr/bin/env bash
# Health check: verify external dependencies are present before running.
set -uo pipefail

ok=0; bad=0
check() {  # check "label" "command..."
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  ✓ $label"; ok=$((ok+1))
  else
    echo "  ✗ $label"; bad=$((bad+1))
  fi
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${HIVEMIND_HOOKS__PORT:-$(grep -E '^\s*port\s*=' "$ROOT/config/hivemind.toml" 2>/dev/null | head -1 | grep -oE '[0-9]+' || echo 8787)}"

echo "==> Hivemind doctor"
check "tmux installed"   command -v tmux
check "claude installed" command -v claude
check "python >= 3.11"   bash -c 'python3 -c "import sys; assert sys.version_info >= (3,11)"'
check ".env present"     test -f "$ROOT/.env"
check "hooks server up"  bash -c "curl -s -m 2 http://127.0.0.1:$PORT/health | grep -q ok"

echo
echo "tmux version: $(tmux -V 2>/dev/null || echo 'n/a')"
echo "sessions:     $(tmux list-sessions 2>/dev/null | grep -c '^cc-' || echo 0) cc-* terminals"
echo "hooks port:   $PORT"

echo
echo "==> $ok ok, $bad problem(s)"
test "$bad" -eq 0
