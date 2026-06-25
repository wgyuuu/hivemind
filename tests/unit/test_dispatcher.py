"""Unit tests for the Dispatcher using a fake manager (no tmux, no SDK)."""

from __future__ import annotations

import pytest

from hivemind.core.registry import Terminal, TerminalError
from hivemind.core.state import TermState
from hivemind.services.dispatcher import Dispatcher


class FakeManager:
    """In-memory stand-in for TerminalManager; records forwarded text."""

    def __init__(self) -> None:
        self._terms: dict[str, Terminal] = {}
        self.sent: list[tuple[str, str]] = []

    def seed(self, name: str, state: TermState = TermState.IDLE) -> None:
        self._terms[name] = Terminal(name=name, session=f"cc-{name}", cwd="~", state=state)

    def get(self, name):
        return self._terms.get(name)

    def all(self):
        return list(self._terms.values())

    def names(self):
        return sorted(self._terms)

    async def spawn(self, name, cwd="~", command="claude"):
        if name in self._terms:
            raise TerminalError(f"terminal {name!r} already exists")
        self.seed(name)
        self._terms[name].cwd = cwd
        return self._terms[name]

    async def kill(self, name):
        if name not in self._terms:
            raise TerminalError(f"terminal {name!r} not found")
        del self._terms[name]


@pytest.fixture
def setup(monkeypatch):
    """Patch forwarder.forward so dispatch never touches tmux."""
    mgr = FakeManager()
    disp = Dispatcher(mgr)

    async def fake_forward(terminal, text, **kw):
        mgr.sent.append((terminal.name, text))

    monkeypatch.setattr("hivemind.services.dispatcher.forwarder.forward", fake_forward)
    return mgr, disp


async def test_send_to_named_terminal_sets_default(setup):
    mgr, disp = setup
    mgr.seed("web")
    reply = await disp.handle("@web build it")
    assert ("web", "build it") in mgr.sent
    assert disp.default_target == "web"
    assert "web" in reply


async def test_bare_text_uses_sticky_default(setup):
    mgr, disp = setup
    mgr.seed("web")
    await disp.handle("@web first")
    await disp.handle("second")
    assert ("web", "second") in mgr.sent


async def test_send_to_missing_terminal_warns(setup):
    mgr, disp = setup
    reply = await disp.handle("@ghost hello")
    assert "不存在" in reply
    assert mgr.sent == []


async def test_send_without_default_prompts(setup):
    mgr, disp = setup
    reply = await disp.handle("hello with no target")
    assert "默认终端" in reply


async def test_ls_lists_terminals(setup):
    mgr, disp = setup
    mgr.seed("web")
    mgr.seed("infra")
    reply = await disp.handle("/ls")
    assert "web" in reply and "infra" in reply


async def test_spawn_then_kill(setup):
    mgr, disp = setup
    r1 = await disp.handle("/spawn api ~/code/api")
    assert "api" in r1
    assert disp.default_target == "api"
    r2 = await disp.handle("/kill api")
    assert "api" in r2
    assert disp.default_target is None


async def test_confirm_types_digit(setup):
    mgr, disp = setup
    mgr.seed("web", state=TermState.WAITING)
    await disp.handle("@web")          # set default
    await disp.handle("/y")
    assert ("web", "1") in mgr.sent


async def test_help(setup):
    _, disp = setup
    assert "指令帮助" in await disp.handle("/help")
