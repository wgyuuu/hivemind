#!/usr/bin/env bash
# Install / uninstall the Hivemind launchd agent.
# Usage: deploy/install-service.sh [install|uninstall]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.hivemind.bridge"
SRC="$ROOT/deploy/launchd/$LABEL.plist"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
ACTION="${1:-install}"

case "$ACTION" in
  install)
    mkdir -p "$ROOT/var/logs" "$HOME/Library/LaunchAgents"
    sed "s#@ROOT@#$ROOT#g" "$SRC" > "$DEST"
    launchctl unload "$DEST" 2>/dev/null || true
    launchctl load "$DEST"
    echo "==> Loaded $LABEL"
    echo "    logs: $ROOT/var/logs/launchd.{out,err}.log"
    ;;
  uninstall)
    launchctl unload "$DEST" 2>/dev/null || true
    rm -f "$DEST"
    echo "==> Unloaded and removed $LABEL"
    ;;
  *)
    echo "usage: $0 [install|uninstall]" >&2
    exit 2
    ;;
esac
