"""tmux adapter — the only place that shells out to `tmux`.

Wraps new-session / kill-session / list-sessions / send-keys / capture-pane.
Keeping this isolated means swapping to another multiplexer (e.g. zellij) later
only touches this file.

Naming: a Hivemind terminal called "web" is backed by tmux session "cc-web".
Functions here take the SHORT name (e.g. "web") and apply the prefix internally.
"""

from __future__ import annotations

import os

from hivemind.utils.shell import CommandError, run_cmd

SESSION_PREFIX = "cc-"


def session_name(name: str) -> str:
    """Map a short terminal name to its tmux session name."""
    return f"{SESSION_PREFIX}{name}"


def short_name(session: str) -> str:
    """Inverse of session_name(); strips the cc- prefix."""
    return session[len(SESSION_PREFIX):] if session.startswith(SESSION_PREFIX) else session


async def list_sessions() -> list[str]:
    """Return the SHORT names of existing cc-* tmux sessions (sorted)."""
    try:
        out = await run_cmd("tmux", "list-sessions", "-F", "#{session_name}")
    except CommandError:
        # `no server running` -> no sessions yet.
        return []
    names = [
        short_name(line.strip())
        for line in out.splitlines()
        if line.strip().startswith(SESSION_PREFIX)
    ]
    return sorted(names)


async def has_session(name: str) -> bool:
    """True if the cc-<name> session exists."""
    try:
        await run_cmd("tmux", "has-session", "-t", session_name(name))
        return True
    except CommandError:
        return False


async def new_session(name: str, cwd: str, command: str) -> None:
    """Create a detached tmux session running `command` in `cwd`.

    `cwd` may contain ~ which is expanded here. HIVEMIND_TERM is exported inside
    the session so claude-hooks can tag events with the terminal name (M3).
    """
    cwd_expanded = os.path.expanduser(cwd)  # noqa: ASYNC240 (pure string op, no I/O)
    wrapped = f"HIVEMIND_TERM={name} {command}"
    await run_cmd(
        "tmux", "new-session", "-d",
        "-s", session_name(name),
        "-c", cwd_expanded,
        wrapped,
    )


async def kill_session(name: str) -> None:
    """Kill the cc-<name> session. Idempotent: missing session is not an error."""
    if await has_session(name):
        await run_cmd("tmux", "kill-session", "-t", session_name(name))


async def capture_pane(name: str, lines: int = 200) -> str:
    """Return the last `lines` of the pane as plain text (no escape codes)."""
    out = await run_cmd(
        "tmux", "capture-pane", "-p", "-t", session_name(name), "-S", f"-{lines}"
    )
    return out


async def send_escape(name: str) -> None:
    """Send a bare Escape key to clear half-typed input / dismiss menus."""
    await run_cmd("tmux", "send-keys", "-t", session_name(name), "Escape")


async def send_literal(name: str, text: str) -> None:
    """Type `text` literally (no key-name interpretation), WITHOUT pressing Enter."""
    await run_cmd("tmux", "send-keys", "-t", session_name(name), "-l", text)


async def send_enter(name: str) -> None:
    """Press Enter as a standalone key (submit)."""
    await run_cmd("tmux", "send-keys", "-t", session_name(name), "Enter")
