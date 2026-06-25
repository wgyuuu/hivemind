"""Terminal registry: model + manager for the set of Claude terminals.

Each terminal maps 1:1 to a tmux session named `cc-<name>`. The registry is the
single source of truth for which terminals exist and their last-known state.
The manager delegates all tmux I/O to adapters.tmux so it stays testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from hivemind.adapters import tmux
from hivemind.core.state import TermState

log = logging.getLogger(__name__)

try:  # py311+ stdlib
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


class TerminalError(RuntimeError):
    """Raised on invalid terminal operations (duplicate / missing name)."""


@dataclass
class Terminal:
    """One Claude Code terminal backed by a tmux session."""

    name: str
    session: str               # tmux session name, e.g. "cc-web"
    cwd: str
    command: str = "claude"
    state: TermState = TermState.IDLE
    last_snapshot: str = ""    # last capture-pane text (diff baseline)
    meta: dict = field(default_factory=dict)


class TerminalManager:
    """Create / list / kill terminals and track their state.

    TODO(M2): Monitor updates `state` + `last_snapshot` via update_state().
    TODO(M4): self-healing — recreate a session that died unexpectedly.
    """

    def __init__(self) -> None:
        self._terminals: dict[str, Terminal] = {}

    # -- lookups -----------------------------------------------------------
    def get(self, name: str) -> Terminal | None:
        return self._terminals.get(name)

    def all(self) -> list[Terminal]:
        return list(self._terminals.values())

    def names(self) -> list[str]:
        return sorted(self._terminals)

    # -- lifecycle ---------------------------------------------------------
    async def spawn(self, name: str, cwd: str, command: str = "claude") -> Terminal:
        """Create a new terminal + its tmux session. Errors if name is taken."""
        if name in self._terminals:
            raise TerminalError(f"terminal {name!r} already exists")
        await tmux.new_session(name, cwd=cwd, command=command)
        term = Terminal(name=name, session=tmux.session_name(name), cwd=cwd, command=command)
        self._terminals[name] = term
        log.info("spawned terminal %s (session=%s cwd=%s)", name, term.session, cwd)
        return term

    async def kill(self, name: str) -> None:
        """Kill the terminal's tmux session and drop it from the registry."""
        if name not in self._terminals:
            raise TerminalError(f"terminal {name!r} not found")
        await tmux.kill_session(name)
        del self._terminals[name]
        log.info("killed terminal %s", name)

    def update_state(self, name: str, state: TermState, snapshot: str | None = None) -> None:
        """Record the latest observed state/snapshot (called by Monitor in M2)."""
        term = self._terminals.get(name)
        if term is None:
            return
        term.state = state
        if snapshot is not None:
            term.last_snapshot = snapshot

    # -- bootstrap ---------------------------------------------------------
    async def load_presets(self, terminals_toml: Path) -> None:
        """Spawn terminals declared in config/terminals.toml that aren't running.

        Reconciles with tmux: a preset whose session already exists is adopted
        (registered) rather than re-spawned, so a Bridge restart is seamless.
        """
        presets = _read_presets(terminals_toml)
        existing = set(await tmux.list_sessions())
        for p in presets:
            name = p["name"]
            if name in self._terminals:
                continue
            if name in existing:
                self._terminals[name] = Terminal(
                    name=name,
                    session=tmux.session_name(name),
                    cwd=p.get("cwd", "~"),
                    command=p.get("command", "claude"),
                )
                log.info("adopted existing session for terminal %s", name)
            else:
                await self.spawn(name, cwd=p.get("cwd", "~"), command=p.get("command", "claude"))


def _read_presets(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return list(data.get("terminal", []))
