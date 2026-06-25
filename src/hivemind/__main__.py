"""Console entry point: `python -m hivemind` / `hivemind`."""

from __future__ import annotations

import asyncio
import sys


def main() -> int:
    """Synchronous wrapper around the async Bridge runtime.

    Returns a process exit code so launchd / shells can react to failures.
    """
    from hivemind.bridge import run

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
