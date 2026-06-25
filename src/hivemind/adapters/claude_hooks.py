"""Claude Code hooks — event payload models.

Claude can POST lifecycle events (Stop, Notification, PostToolUse, ...) to a local
endpoint. These models describe the payload; services.hooks_server receives them
and feeds the Monitor authoritative, low-latency signals (vs fragile screen
scraping).
"""

from __future__ import annotations

import enum

from pydantic import BaseModel


class HookEvent(enum.StrEnum):
    STOP = "Stop"                    # Claude finished responding
    NOTIFICATION = "Notification"    # Claude needs attention (e.g. permission)
    POST_TOOL_USE = "PostToolUse"
    SESSION_START = "SessionStart"


class HookPayload(BaseModel):
    """Normalized hook event coming from a cc-<name> terminal."""

    event: HookEvent
    terminal: str                    # which cc-<name> emitted it
    message: str = ""
    extra: dict = {}
