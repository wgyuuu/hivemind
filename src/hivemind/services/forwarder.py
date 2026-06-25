"""Forwarder — safely inject a command into a Claude terminal.

Safety protocol (critical, learned the hard way):
  1. send Escape first to clear any half-typed input / dismiss menus
  2. send the instruction as a LITERAL string (`send-keys -l`) so special
     chars are not interpreted as tmux key names
  3. send Enter as a SEPARATE key press (never bundled with the text), so a
     newline inside the text cannot prematurely submit

A small settle delay between steps gives the TUI time to repaint. Only forwards
when the terminal is not BUSY; BUSY terminals queue (M4).
"""

from __future__ import annotations

import asyncio
import logging

from hivemind.adapters import tmux
from hivemind.core.registry import Terminal
from hivemind.core.state import TermState

log = logging.getLogger(__name__)

# Delay between Escape -> type -> Enter so the Claude TUI can repaint.
_SETTLE_S = 0.15


async def forward(terminal: Terminal, text: str, *, settle_s: float = _SETTLE_S) -> None:
    """Inject `text` into `terminal` following the safety protocol."""
    if not text:
        return
    if terminal.state is TermState.BUSY:
        # In M1 we still send, but warn; M4 introduces real queueing.
        log.warning("forwarding to BUSY terminal %s (no queue yet)", terminal.name)
    if terminal.state is TermState.DEAD:
        raise RuntimeError(f"terminal {terminal.name!r} is dead")

    name = terminal.name
    await tmux.send_escape(name)
    await asyncio.sleep(settle_s)
    await tmux.send_literal(name, text)
    await asyncio.sleep(settle_s)
    await tmux.send_enter(name)
    log.info("forwarded %d chars to terminal %s", len(text), name)
