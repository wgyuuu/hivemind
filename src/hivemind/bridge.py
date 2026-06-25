"""Bridge — the long-running asyncio orchestrator.

Wires together: config -> adapters (dingtalk/tmux) -> core (registry) ->
services (router/dispatcher/forwarder/monitor). Owns the process lifecycle:
startup (create var dirs, restore registry from presets, connect DingTalk),
a reconnect supervisor around the Stream client, a background Monitor poll loop,
and graceful shutdown.

This module is intentionally thin: it only *orchestrates*. Real logic lives in
core/ and services/.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from hivemind.adapters.dingtalk import DingTalkClient, IncomingMessage
from hivemind.config import Settings, load_settings
from hivemind.core.registry import TerminalManager
from hivemind.services.dispatcher import Dispatcher
from hivemind.services.hooks_server import HooksServer
from hivemind.services.monitor import Monitor
from hivemind.utils.logging import setup_logging

log = logging.getLogger(__name__)

# Backoff bounds for the DingTalk reconnect supervisor.
_RECONNECT_MIN_S = 1.0
_RECONNECT_MAX_S = 30.0


async def run() -> None:
    """Boot the Bridge and block until cancelled."""
    settings = load_settings()
    setup_logging(settings)
    settings.ensure_runtime_dirs()
    log.info("Hivemind bridge starting (var_dir=%s)", settings.var_dir)

    manager = TerminalManager()
    await _restore_terminals(manager, settings)

    dispatcher = Dispatcher(manager)
    client = DingTalkClient(settings, _make_on_message(dispatcher))

    # Monitor pushes proactively via the DingTalk client's session webhook.
    async def notifier(title: str, text: str) -> bool:
        return await client.push_markdown(title, text)

    monitor = Monitor(
        manager,
        notifier,
        interval_s=settings.monitor.poll_interval_sec,
        capture_lines=settings.monitor.capture_lines,
    )

    tasks: list[asyncio.Task] = [
        asyncio.create_task(_supervise(client), name="dingtalk-supervisor"),
        asyncio.create_task(monitor.poll_loop(), name="monitor"),
    ]

    # M3: local HTTP endpoint that receives Claude hooks as authoritative signals.
    if settings.hooks.enabled:
        hooks = HooksServer(
            host=settings.hooks.host,
            port=settings.hooks.port,
            on_event=monitor.handle_hook,
        )
        tasks.append(asyncio.create_task(hooks.serve_forever(), name="hooks-server"))
    try:
        # If either task raises unexpectedly, surface it; normally they run forever.
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        await _shutdown(tasks)
        log.info("Hivemind bridge stopped")


def _make_on_message(dispatcher: Dispatcher):
    async def on_message(msg: IncomingMessage) -> str:
        log.info("msg from %s (%s): %s", msg.sender_name, msg.sender_id, msg.text)
        # TODO(M4): whitelist gate on msg.sender_id before dispatching.
        return await dispatcher.handle(msg.text)

    return on_message


async def _restore_terminals(manager: TerminalManager, settings: Settings) -> None:
    """Spawn/adopt preset terminals; tolerate tmux not being ready yet."""
    try:
        await manager.load_presets(settings.terminals_toml)
        log.info("terminals ready: %s", manager.names() or "(none)")
    except Exception:
        log.exception("failed to load preset terminals (continuing empty)")


async def _supervise(client: DingTalkClient) -> None:
    """Run the Stream client, reconnecting with exponential backoff on failure."""
    delay = _RECONNECT_MIN_S
    while True:
        try:
            await client.start()
            delay = _RECONNECT_MIN_S  # clean return = normal close; reset backoff
        except asyncio.CancelledError:
            raise
        except Exception as e:  # network blip, auth refresh, etc.
            log.warning("DingTalk client disconnected (%s); retry in %.1fs", e, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, _RECONNECT_MAX_S)


async def _shutdown(tasks: list[asyncio.Task]) -> None:
    """Cancel background tasks and await their teardown."""
    for t in tasks:
        t.cancel()
    for t in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await t
