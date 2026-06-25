"""Unit tests for the Monitor poll loop + transition→notify logic.

We monkeypatch hivemind.services.monitor.tmux.capture_pane to feed scripted pane
text, so no real tmux is needed. The notifier is a fake that records calls.
"""

from __future__ import annotations

import pytest

from hivemind.core.registry import Terminal, TerminalManager
from hivemind.core.state import TermState
from hivemind.services import monitor as monitor_mod
from hivemind.services.monitor import Monitor

# Reusable scripted panes keyed by the state we want detect_state to infer.
PANES = {
    TermState.BUSY: "✻ Working… (esc to interrupt · 5s)",
    TermState.IDLE: "Done.\n╭─\n│ >\n? for shortcuts",
    TermState.WAITING: "Do you want to proceed?\n❯ 1. Yes\n  2. No",
    TermState.ERROR: "Traceback (most recent call last):\nError: boom",
}


def _manager_with(name: str) -> TerminalManager:
    m = TerminalManager()
    m._terminals[name] = Terminal(name=name, session=f"cc-{name}", cwd="/tmp")
    return m


class FakeNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, title: str, text: str) -> bool:
        self.calls.append((title, text))
        return True


@pytest.fixture
def patch_capture(monkeypatch):
    """Returns a setter; the next capture_pane call yields the queued pane."""
    state = {"pane": ""}

    async def fake_capture(name: str, lines: int = 200) -> str:
        return state["pane"]

    monkeypatch.setattr(monitor_mod.tmux, "capture_pane", fake_capture)
    return state


async def test_no_notify_on_first_observation(patch_capture):
    patch_capture["pane"] = PANES[TermState.IDLE]
    notifier = FakeNotifier()
    mon = Monitor(_manager_with("web"), notifier)
    await mon.tick()
    assert notifier.calls == []  # first observation only records baseline


async def test_busy_to_idle_notifies_completion(patch_capture):
    notifier = FakeNotifier()
    mgr = _manager_with("web")
    mon = Monitor(mgr, notifier)

    patch_capture["pane"] = PANES[TermState.BUSY]
    await mon.tick()                       # baseline = BUSY, no notify
    patch_capture["pane"] = PANES[TermState.IDLE]
    await mon.tick()                       # BUSY -> IDLE = completion

    assert len(notifier.calls) == 1
    title, _ = notifier.calls[0]
    assert "完成" in title and "web" in title
    assert mgr.get("web").state is TermState.IDLE


async def test_to_waiting_notifies(patch_capture):
    notifier = FakeNotifier()
    mon = Monitor(_manager_with("web"), notifier)

    patch_capture["pane"] = PANES[TermState.BUSY]
    await mon.tick()
    patch_capture["pane"] = PANES[TermState.WAITING]
    await mon.tick()

    assert len(notifier.calls) == 1
    assert "等待确认" in notifier.calls[0][0]


async def test_idle_to_busy_is_silent(patch_capture):
    notifier = FakeNotifier()
    mon = Monitor(_manager_with("web"), notifier)

    patch_capture["pane"] = PANES[TermState.IDLE]
    await mon.tick()
    patch_capture["pane"] = PANES[TermState.BUSY]
    await mon.tick()                       # user just sent a command; no spam

    assert notifier.calls == []


async def test_dead_when_capture_fails(patch_capture, monkeypatch):
    from hivemind.utils.shell import CommandError

    notifier = FakeNotifier()
    mgr = _manager_with("web")
    mon = Monitor(mgr, notifier)

    patch_capture["pane"] = PANES[TermState.BUSY]
    await mon.tick()                       # baseline BUSY

    async def boom(name: str, lines: int = 200) -> str:
        raise CommandError(["tmux"], 1, "no session")

    monkeypatch.setattr(monitor_mod.tmux, "capture_pane", boom)
    await mon.tick()                       # BUSY -> DEAD

    assert mgr.get("web").state is TermState.DEAD
    assert len(notifier.calls) == 1
    assert "退出" in notifier.calls[0][0]


# -- M3: hook path (authoritative) ------------------------------------------

from hivemind.adapters.claude_hooks import HookEvent, HookPayload  # noqa: E402


async def test_handle_hook_stop_notifies_completion(patch_capture):
    patch_capture["pane"] = PANES[TermState.IDLE]
    notifier = FakeNotifier()
    mgr = _manager_with("web")
    mon = Monitor(mgr, notifier)

    await mon.handle_hook(HookPayload(event=HookEvent.STOP, terminal="web"))

    assert len(notifier.calls) == 1
    assert "完成" in notifier.calls[0][0]
    assert mgr.get("web").state is TermState.IDLE


async def test_handle_hook_notification_notifies_waiting_with_message(patch_capture):
    patch_capture["pane"] = PANES[TermState.WAITING]
    notifier = FakeNotifier()
    mon = Monitor(_manager_with("web"), notifier)

    await mon.handle_hook(
        HookPayload(event=HookEvent.NOTIFICATION, terminal="web", message="需要授权 rm -rf")
    )

    assert len(notifier.calls) == 1
    title, text = notifier.calls[0]
    assert "等待确认" in title
    assert "需要授权" in text


async def test_handle_hook_unknown_terminal_ignored(patch_capture):
    notifier = FakeNotifier()
    mon = Monitor(_manager_with("web"), notifier)
    await mon.handle_hook(HookPayload(event=HookEvent.STOP, terminal="ghost"))
    assert notifier.calls == []


async def test_hook_then_poll_dedup(patch_capture):
    """A hook and the next poll observing the same transition notify only once."""
    notifier = FakeNotifier()
    mgr = _manager_with("web")
    mon = Monitor(mgr, notifier, dedup_window_s=10.0)

    patch_capture["pane"] = PANES[TermState.BUSY]
    await mon.tick()                       # baseline BUSY

    patch_capture["pane"] = PANES[TermState.IDLE]
    await mon.handle_hook(HookPayload(event=HookEvent.STOP, terminal="web"))  # hook -> IDLE
    await mon.tick()                       # poll also sees IDLE, but deduped

    assert len(notifier.calls) == 1


async def test_dedup_expires_after_window(patch_capture):
    notifier = FakeNotifier()
    mon = Monitor(_manager_with("web"), notifier, dedup_window_s=0.0)

    patch_capture["pane"] = PANES[TermState.WAITING]
    await mon.handle_hook(HookPayload(event=HookEvent.NOTIFICATION, terminal="web"))
    await mon.handle_hook(HookPayload(event=HookEvent.NOTIFICATION, terminal="web"))

    assert len(notifier.calls) == 2  # window=0 means no suppression
