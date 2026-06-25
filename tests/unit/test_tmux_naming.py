"""Pure-logic tests for tmux name mapping (no tmux process needed)."""

from __future__ import annotations

from hivemind.adapters import tmux


def test_session_name_adds_prefix():
    assert tmux.session_name("web") == "cc-web"


def test_short_name_strips_prefix():
    assert tmux.short_name("cc-web") == "web"


def test_short_name_passthrough_when_no_prefix():
    assert tmux.short_name("other") == "other"


def test_roundtrip():
    for n in ("web", "infra", "api-2"):
        assert tmux.short_name(tmux.session_name(n)) == n
