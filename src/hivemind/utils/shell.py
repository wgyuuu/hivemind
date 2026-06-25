"""Safe async subprocess wrapper used by adapters (mainly tmux)."""

from __future__ import annotations

import asyncio


class CommandError(RuntimeError):
    """Raised when a shell command exits non-zero."""

    def __init__(self, argv: list[str], code: int, stderr: str) -> None:
        super().__init__(f"{argv!r} exited {code}: {stderr.strip()}")
        self.argv = argv
        self.code = code
        self.stderr = stderr


async def run_cmd(*argv: str) -> str:
    """Run argv (no shell), return stdout, raise CommandError on failure."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise CommandError(list(argv), proc.returncode or -1, err.decode())
    return out.decode()
