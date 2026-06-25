"""Unit tests for the addressing/command parser (pure logic, offline)."""

from __future__ import annotations

from hivemind.services.router import Verb, parse


def test_address_prefix_routes_to_named_terminal():
    d = parse("@web build the landing page", default_target=None)
    assert d.verb is Verb.SEND
    assert d.target == "web"
    assert d.text == "build the landing page"


def test_bare_text_uses_default_target():
    d = parse("run the tests", default_target="infra")
    assert d.verb is Verb.SEND
    assert d.target == "infra"
    assert d.text == "run the tests"


def test_address_only_switches_default():
    d = parse("@web", default_target="infra")
    assert d.verb is Verb.SEND
    assert d.target == "web"
    assert d.text == ""


def test_empty_message_is_unknown():
    d = parse("   ", default_target=None)
    assert d.verb is Verb.UNKNOWN
    assert d.error


def test_ls_command():
    assert parse("/ls").verb is Verb.LS
    assert parse("/list").verb is Verb.LS


def test_status_with_and_without_target():
    assert parse("/status web").target == "web"
    assert parse("/status").target is None


def test_spawn_parses_name_and_cwd():
    d = parse("/spawn api ~/projects/api")
    assert d.verb is Verb.SPAWN
    assert d.target == "api"
    assert d.args["cwd"] == "~/projects/api"


def test_spawn_without_name_is_error():
    d = parse("/spawn")
    assert d.verb is Verb.SPAWN
    assert d.error


def test_kill_command():
    d = parse("/kill web")
    assert d.verb is Verb.KILL
    assert d.target == "web"


def test_confirm_yes_no():
    assert parse("/y").args["answer"] is True
    assert parse("/n").args["answer"] is False


def test_unknown_slash_command():
    d = parse("/frobnicate")
    assert d.verb is Verb.UNKNOWN
    assert "frobnicate" in (d.error or "")
