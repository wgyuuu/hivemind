"""Integration smoke test against a real tmux (skipped if tmux missing)."""

from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not installed")


@pytest.mark.skip(reason="M1: implement adapters.tmux first")
async def test_spawn_and_kill_session():
    from hivemind.adapters import tmux

    await tmux.new_session("pytest", cwd="/tmp", command="bash")
    assert "pytest" in await tmux.list_sessions()
    await tmux.kill_session("pytest")
