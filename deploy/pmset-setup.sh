#!/usr/bin/env bash
# Keep the Mac awake enough to run Hivemind 24/7, even with the lid closed.
# Requires sudo. Review each setting before applying on your machine.
set -euo pipefail

echo "==> Current power settings:"
pmset -g

cat <<'NOTE'

==> To run 24/7 (AC power), consider:
    sudo pmset -c sleep 0            # never system-sleep on AC
    sudo pmset -c disablesleep 1     # allow lid-closed operation (clamshell)
    sudo pmset -c powernap 1

    Revert with:
    sudo pmset -c disablesleep 0
    sudo pmset -c sleep 1

These are NOT applied automatically. Run the ones you want manually.
NOTE
