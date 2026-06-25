"""Terminal state machine.

Maps a `tmux capture-pane` snapshot of a Claude Code TUI to a coarse TermState.

WARNING — FRAGILE BY NATURE:
    The heuristics rely on Claude Code's current TUI strings (e.g.
    "esc to interrupt", a "❯ 1. Yes" permission menu, the "> " prompt box).
    These can change between Claude versions. Three defenses:
      1. All marker strings live in the *_MARKERS tuples below — recalibrate in
         one place.
      2. tests/fixtures/*.txt hold real captured panes; test_state.py locks the
         mapping so an upstream change fails loudly.
      3. M3 wires claude-hooks events as the AUTHORITATIVE signal; this scraper
         then only needs to be "good enough" for content extraction + a fallback.

Detection order matters: ERROR and WAITING are checked before BUSY/IDLE because
a pane can contain both a spinner remnant and a prompt.
"""

from __future__ import annotations

import enum

# --- TUI marker strings (recalibrate here when Claude's UI changes) ---------

# Claude is actively working: footer shows a cancel hint while streaming.
BUSY_MARKERS: tuple[str, ...] = (
    "esc to interrupt",
    "ctrl+c to interrupt",
    "Thinking…",
    "Thinking...",
)

# Claude is asking for confirmation (tool permission / yes-no menu).
WAITING_MARKERS: tuple[str, ...] = (
    "❯ 1. Yes",
    "1. Yes",
    "Do you want to proceed?",
    "Do you want to make this edit",
    "Would you like to",
    "(y/n)",
)

# A crash / fatal error surfaced in the pane.
ERROR_MARKERS: tuple[str, ...] = (
    "Traceback (most recent call last)",
    "command not found",
    "Error:",
    "panic:",
    "[Process completed]",
    "exited with code",
)

# Idle prompt box waiting for input (the empty Claude composer).
IDLE_MARKERS: tuple[str, ...] = (
    "│ >",
    "╭─",
    "? for shortcuts",
    "Try \"",
)


class TermState(enum.StrEnum):
    """Lifecycle / activity state of a single Claude terminal."""

    BUSY = "busy"          # actively generating / running a tool
    IDLE = "idle"          # prompt ready, waiting for input
    WAITING = "waiting"    # asking the user to confirm (permission prompt)
    ERROR = "error"        # crashed / showing an error
    DEAD = "dead"          # tmux session gone (set by the caller, not here)


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(n in haystack for n in needles)


def detect_state(pane_text: str) -> TermState:
    """Infer TermState from a capture-pane snapshot.

    The empty string (or whitespace only) is treated as IDLE — a freshly
    attached pane that has not painted yet. DEAD is never returned here; the
    Monitor sets it when the tmux session is gone.
    """
    if not pane_text or not pane_text.strip():
        return TermState.IDLE

    # Inspect only the tail: the footer/prompt that reflects current state lives
    # at the bottom of the pane; older scrollback would cause false positives.
    tail = "\n".join(pane_text.splitlines()[-15:])

    # BUSY wins: an active spinner means Claude is working even if a stale menu
    # is still on screen above it.
    if _contains_any(tail, BUSY_MARKERS):
        return TermState.BUSY
    if _contains_any(tail, WAITING_MARKERS):
        return TermState.WAITING
    if _contains_any(tail, ERROR_MARKERS):
        return TermState.ERROR
    if _contains_any(tail, IDLE_MARKERS):
        return TermState.IDLE

    # No known marker: assume IDLE (safe default — we just won't push).
    return TermState.IDLE


def is_attention_state(state: TermState) -> bool:
    """States that warrant a proactive push to the user's phone."""
    return state in (TermState.WAITING, TermState.ERROR, TermState.DEAD)


def clean_tail(pane_text: str, max_lines: int = 20) -> str:
    """Return the last `max_lines` non-blank lines, trimmed for a chat card."""
    lines = [ln.rstrip() for ln in pane_text.splitlines()]
    # Drop trailing blank lines so the card doesn't end with whitespace.
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines[-max_lines:])
