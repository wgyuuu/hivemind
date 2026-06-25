"""Monitor — watch terminals and push state changes to DingTalk.

Hybrid strategy (M2 poll + M3 hooks):
  * claude-hooks events (M3)   -> AUTHORITATIVE, low-latency signal. A `Stop`
                                  event means "finished", a `Notification` means
                                  "needs attention". Routed via handle_hook().
  * capture-pane diff (poll)   -> FALLBACK. Detect state from the TUI every
                                  interval; covers crashes / version skew where
                                  no hook fires (DEAD, ERROR, missed events).

Both paths funnel every notification through _emit(), which applies a short
time-window dedup keyed by (terminal, state). That way a hook and the next poll
observing the same transition never double-notify the phone.

"Meaningful" transitions only: we notify when a terminal finishes (-> IDLE after
BUSY), needs confirmation (-> WAITING), errors (-> ERROR) or dies (-> DEAD). We
never notify IDLE -> BUSY (the user just sent the command).

The notifier is an injected coroutine (title, text) -> Awaitable[bool], so the
Monitor has no dependency on the DingTalk SDK and is fully unit-testable.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from hivemind.adapters import tmux
from hivemind.adapters.claude_hooks import HookEvent, HookPayload
from hivemind.core.registry import TerminalManager
from hivemind.core.state import TermState, clean_tail, detect_state
from hivemind.utils.shell import CommandError

log = logging.getLogger(__name__)

Notifier = Callable[[str, str], Awaitable[bool]]

_STATE_EMOJI = {
    TermState.BUSY: "🟠",
    TermState.IDLE: "🟢",
    TermState.WAITING: "🟡",
    TermState.ERROR: "🔴",
    TermState.DEAD: "⚫️",
}

# Transitions worth a phone push, keyed by the NEW state -> human label.
_NOTIFY_ON = {
    TermState.IDLE: "✅ 完成",
    TermState.WAITING: "🟡 等待确认",
    TermState.ERROR: "🔴 出错",
    TermState.DEAD: "⚫️ 终端已退出",
}

# Map authoritative hook events onto the state they imply.
_HOOK_STATE = {
    HookEvent.STOP: TermState.IDLE,            # Claude finished responding
    HookEvent.NOTIFICATION: TermState.WAITING,  # needs attention / permission
}


class Monitor:
    """Owns the polling loop, the hook intake, and transition→notify logic."""

    def __init__(
        self,
        manager: TerminalManager,
        notifier: Notifier,
        interval_s: float = 2.0,
        capture_lines: int = 200,
        dedup_window_s: float = 10.0,
    ) -> None:
        self._manager = manager
        self._notifier = notifier
        self._interval_s = interval_s
        self._capture_lines = capture_lines
        self._dedup_window_s = dedup_window_s
        # name -> last state we observed, to detect transitions in the poll path.
        self._last_state: dict[str, TermState] = {}
        # name -> (state, monotonic_ts) of the last notification actually emitted.
        self._recent_emit: dict[str, tuple[TermState, float]] = {}

    # -- poll path (fallback) ------------------------------------------------
    async def poll_loop(self) -> None:
        """Poll forever until cancelled."""
        log.info("monitor started (interval=%.1fs)", self._interval_s)
        try:
            while True:
                await self.tick()
                await asyncio.sleep(self._interval_s)
        except asyncio.CancelledError:
            log.info("monitor stopped")
            raise

    async def tick(self) -> None:
        """One polling pass over all terminals. Isolated so tests can call it."""
        for term in self._manager.all():
            try:
                await self._poll_one(term.name)
            except Exception:
                log.exception("monitor poll failed for %s", term.name)

    async def _poll_one(self, name: str) -> None:
        prev = self._last_state.get(name)

        try:
            pane = await tmux.capture_pane(name, lines=self._capture_lines)
            state = detect_state(pane)
        except CommandError:
            pane = ""
            state = TermState.DEAD

        self._manager.update_state(name, state, snapshot=pane or None)

        # First observation: record baseline without notifying (avoid startup spam).
        if prev is None:
            self._last_state[name] = state
            return
        if state == prev:
            return

        self._last_state[name] = state
        log.info("terminal %s: %s -> %s (poll)", name, prev, state)
        if self._should_notify(prev, state):
            await self._emit(name, state, pane, source="poll")

    # -- hook path (authoritative) ------------------------------------------
    async def handle_hook(self, payload: HookPayload) -> None:
        """Process a Claude Code hook event as the authoritative signal.

        Captures a fresh pane for the card body, updates the registry, and emits
        a notification (subject to dedup). Unknown terminals / events are ignored.
        """
        name = payload.terminal
        if self._manager.get(name) is None:
            log.warning("hook for unknown terminal %r ignored", name)
            return
        state = _HOOK_STATE.get(payload.event)
        if state is None:
            log.debug("hook event %s for %s carries no state change", payload.event, name)
            return

        # Best-effort fresh content; fall back to the last snapshot if capture fails.
        pane = ""
        try:
            pane = await tmux.capture_pane(name, lines=self._capture_lines)
        except CommandError:
            term = self._manager.get(name)
            pane = term.last_snapshot if term else ""

        self._manager.update_state(name, state, snapshot=pane or None)
        self._last_state[name] = state
        log.info("terminal %s -> %s (hook:%s)", name, state, payload.event)
        await self._emit(name, state, pane, source="hook", extra=payload.message)

    # -- shared notify path --------------------------------------------------
    async def _emit(
        self,
        name: str,
        state: TermState,
        pane: str,
        *,
        source: str,
        extra: str = "",
    ) -> None:
        """Build a card and notify, unless an identical (name,state) fired recently."""
        now = time.monotonic()
        last = self._recent_emit.get(name)
        if last is not None and last[0] == state and (now - last[1]) < self._dedup_window_s:
            log.debug("dedup %s %s (%s): within window", name, state, source)
            return
        self._recent_emit[name] = (state, now)

        title, text = self._build_card(name, state, pane, extra)
        ok = await self._notifier(title, text)
        if not ok:
            log.debug("notify for %s (%s) not delivered", name, state)

    @staticmethod
    def _should_notify(prev: TermState, new: TermState) -> bool:
        if new not in _NOTIFY_ON:
            return False
        # Becoming idle without having been busy isn't a "completion".
        if new is TermState.IDLE and prev is not TermState.BUSY:
            return False
        return True

    def _build_card(
        self, name: str, state: TermState, pane: str, extra: str = ""
    ) -> tuple[str, str]:
        emoji = _STATE_EMOJI.get(state, "•")
        label = _NOTIFY_ON.get(state, str(state))
        title = f"Hivemind · {name} {label}"
        tail = clean_tail(pane, max_lines=18) if pane else "(无输出)"
        note = f"> {extra}\n\n" if extra else ""
        text = (
            f"### {emoji} `{name}` {label}\n"
            f"{note}"
            f"```\n{tail}\n```\n"
            f"_回复 `@{name} <指令>` 继续，或 `/y` `/n` 应答。_"
        )
        return title, text
