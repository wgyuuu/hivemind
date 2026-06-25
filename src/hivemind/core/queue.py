"""Per-terminal command queue.

A terminal that is BUSY must not receive a second injection (it would race the
running task). Each terminal gets a FIFO queue; the forwarder drains it only
when the terminal is IDLE/WAITING.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class Command:
    """A single queued instruction destined for a terminal."""

    text: str
    sender_id: str
    raw: str = ""


class TerminalQueue:
    """FIFO command queue for one terminal.

    TODO(M4): bound size, drop/notify on overflow, persist across restarts.
    """

    def __init__(self) -> None:
        self._q: asyncio.Queue[Command] = asyncio.Queue()

    async def put(self, cmd: Command) -> None:
        await self._q.put(cmd)

    async def get(self) -> Command:
        return await self._q.get()

    def empty(self) -> bool:
        return self._q.empty()
