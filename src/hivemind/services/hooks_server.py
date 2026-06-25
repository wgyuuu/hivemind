"""Hooks server — tiny local HTTP endpoint that receives Claude Code hook events.

Claude terminals POST lifecycle events here (loopback only) via the hooks
configured in ~/.claude/settings.json (see assets/claude-hooks/). This gives the
Monitor an AUTHORITATIVE, low-latency signal instead of relying purely on screen
scraping.

Security: binds to 127.0.0.1 by default — never expose externally. The payload
is small and validated against HookPayload; malformed bodies get a 400.

Endpoints:
  POST /event   -> {"event": "Stop"|"Notification"|..., "terminal": "web", ...}
  GET  /health  -> {"ok": true}  (used by scripts/doctor.sh)
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from aiohttp import web
from pydantic import ValidationError

from hivemind.adapters.claude_hooks import HookPayload

log = logging.getLogger(__name__)

OnEvent = Callable[[HookPayload], Awaitable[None]]


def make_app(on_event: OnEvent) -> web.Application:
    """Build the aiohttp application (separated so tests can use a test client)."""
    app = web.Application()

    async def handle_event(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        try:
            payload = HookPayload.model_validate(body)
        except ValidationError as e:
            log.warning("rejected hook payload: %s", e)
            return web.json_response({"error": "invalid payload"}, status=400)

        log.debug("hook event %s for %s", payload.event, payload.terminal)
        try:
            await on_event(payload)
        except Exception:
            log.exception("on_event handler failed for %s", payload.terminal)
            # We still ACK: the hook fired correctly; our handling is our problem.
        return web.json_response({"ok": True})

    async def handle_health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app.add_routes(
        [
            web.post("/event", handle_event),
            web.get("/health", handle_health),
        ]
    )
    return app


class HooksServer:
    """Runs make_app() on 127.0.0.1:<port> via an aiohttp AppRunner."""

    def __init__(self, host: str, port: int, on_event: OnEvent) -> None:
        self._host = host
        self._port = port
        self._on_event = on_event
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = make_app(self._on_event)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host=self._host, port=self._port)
        await site.start()
        log.info("hooks server listening on http://%s:%d/event", self._host, self._port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            log.info("hooks server stopped")

    async def serve_forever(self) -> None:
        """Start and block until cancelled (for use as a background task)."""
        import asyncio

        await self.start()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise
        finally:
            await self.stop()
