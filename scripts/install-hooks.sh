#!/usr/bin/env bash
# Merge Hivemind's Claude hooks template into ~/.claude/settings.json.
# Substitutes the hooks port (from config/hivemind.toml, default 8787) and
# backs up the existing settings first. `jq` is recommended for a clean merge.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT/assets/claude-hooks/settings.hooks.json"
TARGET="${CLAUDE_HOME:-$HOME/.claude}/settings.json"

# Resolve the hooks port: env override > config/hivemind.toml > default.
PORT="${HIVEMIND_HOOKS__PORT:-}"
if [[ -z "$PORT" && -f "$ROOT/config/hivemind.toml" ]]; then
  PORT="$(grep -E '^\s*port\s*=' "$ROOT/config/hivemind.toml" | head -1 | grep -oE '[0-9]+' || true)"
fi
PORT="${PORT:-8787}"
echo "==> Using hooks port $PORT"

mkdir -p "$(dirname "$TARGET")"

# Render the template: drop the _comment key and substitute @PORT@.
RENDERED="$(mktemp)"
trap 'rm -f "$RENDERED"' EXIT
sed "s/@PORT@/$PORT/g" "$TEMPLATE" \
  | { jq 'del(._comment)' 2>/dev/null || cat; } > "$RENDERED"

if [[ -f "$TARGET" ]]; then
  cp "$TARGET" "$TARGET.bak.$(date +%s)"
  echo "==> Backed up existing settings.json"
fi

if command -v jq >/dev/null 2>&1 && [[ -f "$TARGET" ]]; then
  # Merge: keep existing settings, overlay our hooks.* keys.
  jq -s '.[0] * {hooks: ((.[0].hooks // {}) * .[1].hooks)}' "$TARGET" "$RENDERED" > "$TARGET.tmp"
  mv "$TARGET.tmp" "$TARGET"
else
  cp "$RENDERED" "$TARGET"
fi

echo "==> Installed hooks into $TARGET"
echo "    Each tmux session exports HIVEMIND_TERM=<name> so events are tagged."
echo "    Verify the server: curl -s http://127.0.0.1:$PORT/health"
