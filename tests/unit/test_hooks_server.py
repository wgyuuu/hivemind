"""Tests for the local hooks HTTP server.

We bind a real HooksServer on an ephemeral loopback port and drive it with an
aiohttp client, so the routing + validation path is exercised end-to-end without
needing the aiohttp pytest plugin.
"""

from __future__ import annotations

import socket

import aiohttp
import pytest

from hivemind.adapters.claude_hooks import HookEvent, HookPayload
from hivemind.services.hooks_server import HooksServer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Collector:
    def __init__(self) -> None:
        self.events: list[HookPayload] = []

    async def __call__(self, payload: HookPayload) -> None:
        self.events.append(payload)


@pytest.fixture
async def server():
    collector = Collector()
    port = _free_port()
    srv = HooksServer(host="127.0.0.1", port=port, on_event=collector)
    await srv.start()
    try:
        yield port, collector
    finally:
        await srv.stop()


async def test_valid_event_is_dispatched(server):
    port, collector = server
    async with aiohttp.ClientSession() as cs:
        async with cs.post(
            f"http://127.0.0.1:{port}/event",
            json={"event": "Stop", "terminal": "web"},
        ) as resp:
            assert resp.status == 200
            assert (await resp.json())["ok"] is True

    assert len(collector.events) == 1
    assert collector.events[0].event is HookEvent.STOP
    assert collector.events[0].terminal == "web"


async def test_invalid_payload_returns_400(server):
    port, collector = server
    async with aiohttp.ClientSession() as cs:
        async with cs.post(
            f"http://127.0.0.1:{port}/event",
            json={"event": "NotARealEvent", "terminal": "web"},
        ) as resp:
            assert resp.status == 400
    assert collector.events == []


async def test_malformed_json_returns_400(server):
    port, collector = server
    async with aiohttp.ClientSession() as cs:
        async with cs.post(
            f"http://127.0.0.1:{port}/event",
            data="not json",
            headers={"Content-Type": "application/json"},
        ) as resp:
            assert resp.status == 400
    assert collector.events == []


async def test_health_endpoint(server):
    port, _ = server
    async with aiohttp.ClientSession() as cs:
        async with cs.get(f"http://127.0.0.1:{port}/health") as resp:
            assert resp.status == 200
            assert (await resp.json())["ok"] is True


async def test_handler_exception_still_acks(server):
    # on_event raising must not 500 — the hook fired correctly.
    port = _free_port()

    async def boom(payload: HookPayload) -> None:
        raise RuntimeError("handler blew up")

    srv = HooksServer(host="127.0.0.1", port=port, on_event=boom)
    await srv.start()
    try:
        async with aiohttp.ClientSession() as cs:
            async with cs.post(
                f"http://127.0.0.1:{port}/event",
                json={"event": "Stop", "terminal": "web"},
            ) as resp:
                assert resp.status == 200
    finally:
        await srv.stop()
