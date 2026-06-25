"""Unit tests for the terminal state machine.

The fixtures under tests/fixtures/ are real-ish capture-pane samples. They lock
detect_state's mapping so an upstream Claude TUI change fails loudly here.
"""

from __future__ import annotations

import pytest

from hivemind.core.state import (
    TermState,
    clean_tail,
    detect_state,
    is_attention_state,
)


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("busy.txt", TermState.BUSY),
        ("idle.txt", TermState.IDLE),
        ("waiting.txt", TermState.WAITING),
        ("error.txt", TermState.ERROR),
    ],
)
def test_detect_state_from_fixture(pane_sample, fixture, expected):
    assert detect_state(pane_sample(fixture)) is expected


def test_empty_pane_is_idle():
    assert detect_state("") is TermState.IDLE
    assert detect_state("   \n  \n") is TermState.IDLE


def test_busy_beats_stale_menu_above():
    # A leftover permission menu plus an active spinner -> still BUSY.
    pane = "❯ 1. Yes\n   2. No\n\n✻ Working… (esc to interrupt · 3s)"
    assert detect_state(pane) is TermState.BUSY


def test_attention_states():
    assert is_attention_state(TermState.WAITING)
    assert is_attention_state(TermState.ERROR)
    assert is_attention_state(TermState.DEAD)
    assert not is_attention_state(TermState.BUSY)
    assert not is_attention_state(TermState.IDLE)


def test_clean_tail_trims_trailing_blanks_and_limits():
    text = "a\nb\nc\nd\n\n\n"
    assert clean_tail(text, max_lines=2) == "c\nd"
