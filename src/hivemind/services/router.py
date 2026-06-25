"""Router — parse the DingTalk addressing/command grammar.

Grammar (v1):
    @<name> <text>     route <text> to terminal <name>; sets it as the default
    <text>             route to the current default terminal (session stickiness)
    /ls                list terminals + states
    /status [<name>]   show last snapshot/state
    /spawn <name> [cwd]  create a new terminal
    /kill <name>       kill a terminal
    /y  /n             answer a WAITING confirmation prompt
    /help              show help card

`parse` is pure: it only classifies intent. It never touches tmux or the
registry — the dispatcher executes the resulting Directive.
"""

from __future__ import annotations

import enum
import shlex
from dataclasses import dataclass, field


class Verb(enum.StrEnum):
    SEND = "send"
    LS = "ls"
    STATUS = "status"
    SPAWN = "spawn"
    KILL = "kill"
    CONFIRM = "confirm"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class Directive:
    """Parsed user intent."""

    verb: Verb
    target: str | None = None      # terminal name, if addressed/required
    text: str = ""                 # payload for SEND
    args: dict = field(default_factory=dict)
    error: str | None = None       # set when a command is malformed


def parse(message: str, default_target: str | None = None) -> Directive:
    """Parse a raw DingTalk message into a Directive."""
    msg = (message or "").strip()
    if not msg:
        return Directive(verb=Verb.UNKNOWN, error="empty message")

    if msg.startswith("/"):
        return _parse_command(msg)

    if msg.startswith("@"):
        return _parse_address(msg, default_target)

    # Bare text -> send to the sticky default terminal.
    return Directive(verb=Verb.SEND, target=default_target, text=msg)


def _parse_address(msg: str, default_target: str | None) -> Directive:
    # "@web build the site" -> target=web, text="build the site"
    body = msg[1:].lstrip()
    name, _, rest = body.partition(" ")
    if not name:
        return Directive(verb=Verb.UNKNOWN, error="missing terminal name after @")
    text = rest.strip()
    if not text:
        # "@web" alone just switches the default terminal.
        return Directive(verb=Verb.SEND, target=name, text="")
    return Directive(verb=Verb.SEND, target=name, text=text)


def _parse_command(msg: str) -> Directive:
    try:
        parts = shlex.split(msg)
    except ValueError:
        parts = msg.split()
    cmd = parts[0][1:].lower()        # strip leading '/'
    rest = parts[1:]

    match cmd:
        case "ls" | "list":
            return Directive(verb=Verb.LS)
        case "status":
            return Directive(verb=Verb.STATUS, target=rest[0] if rest else None)
        case "spawn":
            if not rest:
                return Directive(verb=Verb.SPAWN, error="usage: /spawn <name> [cwd]")
            return Directive(
                verb=Verb.SPAWN,
                target=rest[0],
                args={"cwd": rest[1] if len(rest) > 1 else "~"},
            )
        case "kill":
            if not rest:
                return Directive(verb=Verb.KILL, error="usage: /kill <name>")
            return Directive(verb=Verb.KILL, target=rest[0])
        case "y" | "yes":
            return Directive(verb=Verb.CONFIRM, args={"answer": True})
        case "n" | "no":
            return Directive(verb=Verb.CONFIRM, args={"answer": False})
        case "help" | "h":
            return Directive(verb=Verb.HELP)
        case _:
            return Directive(verb=Verb.UNKNOWN, error=f"unknown command: /{cmd}")
