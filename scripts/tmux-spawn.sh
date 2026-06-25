#!/usr/bin/env bash
# Manually spawn a Claude terminal as a detached tmux session cc-<name>.
# Usage: scripts/tmux-spawn.sh <name> [cwd] [command]
set -euo pipefail

name="${1:?usage: tmux-spawn.sh <name> [cwd] [command]}"
cwd="${2:-$PWD}"
cmd="${3:-claude}"
session="cc-$name"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "==> Session $session already exists"
  exit 0
fi

# HIVEMIND_TERM lets claude-hooks tag events with the terminal name.
tmux new-session -d -s "$session" -c "$cwd" \
  "HIVEMIND_TERM=$name $cmd"

echo "==> Spawned $session (cwd=$cwd, cmd=$cmd)"
echo "    Attach with: tmux attach -t $session"
