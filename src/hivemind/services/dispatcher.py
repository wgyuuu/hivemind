"""Dispatcher — execute a parsed Directive against the registry/forwarder.

This is the heart of M1's request/reply loop:

    raw text --router.parse--> Directive --dispatch--> (side effects) + reply str

The dispatcher holds the per-conversation "default terminal" stickiness so a bare
message (no @name) goes to the last-addressed terminal. It returns Markdown text
that the DingTalk adapter sends straight back to the user.

Kept free of SDK types so it is unit-testable with a fake manager.
"""

from __future__ import annotations

import logging

from hivemind.core.registry import TerminalError, TerminalManager
from hivemind.services import forwarder, router
from hivemind.services.router import Directive, Verb

log = logging.getLogger(__name__)

_STATE_EMOJI = {
    "busy": "🟠",
    "idle": "🟢",
    "waiting": "🟡",
    "error": "🔴",
    "dead": "⚫️",
}


class Dispatcher:
    """Turns Directives into actions and Markdown replies."""

    def __init__(self, manager: TerminalManager) -> None:
        self._manager = manager
        self._default_target: str | None = None

    async def handle(self, text: str) -> str:
        """Parse + execute a raw user message, returning Markdown reply text."""
        directive = router.parse(text, default_target=self._default_target)
        return await self.dispatch(directive)

    async def dispatch(self, d: Directive) -> str:
        if d.error:
            return f"⚠️ {d.error}"
        match d.verb:
            case Verb.SEND:
                return await self._do_send(d)
            case Verb.LS:
                return self._do_ls()
            case Verb.STATUS:
                return self._do_status(d.target)
            case Verb.SPAWN:
                return await self._do_spawn(d)
            case Verb.KILL:
                return await self._do_kill(d.target)
            case Verb.CONFIRM:
                return await self._do_confirm(d)
            case Verb.HELP:
                return self._help_text()
            case _:
                return "❓ 无法识别的指令。发送 `/help` 查看用法。"

    # -- verbs -------------------------------------------------------------
    async def _do_send(self, d: Directive) -> str:
        target = d.target or self._default_target
        if not target:
            return "⚠️ 还没有默认终端。用 `@<name> 指令` 指定一个，或 `/ls` 查看。"
        term = self._manager.get(target)
        if term is None:
            return f"⚠️ 终端 `{target}` 不存在。`/ls` 查看现有终端。"
        # Update stickiness even if the message body is empty (pure switch).
        self._default_target = target
        if not d.text:
            return f"✅ 已切换默认终端为 `{target}`。"
        await forwarder.forward(term, d.text)
        return f"📨 已发送给 `{target}`：\n> {d.text}"

    def _do_ls(self) -> str:
        terms = self._manager.all()
        if not terms:
            return "（暂无终端）用 `/spawn <name>` 新建一个。"
        lines = ["### 🧠 终端列表"]
        for t in sorted(terms, key=lambda x: x.name):
            emoji = _STATE_EMOJI.get(str(t.state), "•")
            marker = " ⭐️" if t.name == self._default_target else ""
            lines.append(f"- {emoji} **{t.name}** · `{t.session}` — {t.state}{marker}")
        return "\n".join(lines)

    def _do_status(self, target: str | None) -> str:
        name = target or self._default_target
        if not name:
            return "⚠️ 指定一个终端：`/status <name>`。"
        term = self._manager.get(name)
        if term is None:
            return f"⚠️ 终端 `{name}` 不存在。"
        snapshot = term.last_snapshot.strip() or "(暂无快照，等待 M2 监控)"
        # Keep the card small; show the tail of the pane.
        tail = "\n".join(snapshot.splitlines()[-20:])
        return f"### `{name}` · {term.state}\n```\n{tail}\n```"

    async def _do_spawn(self, d: Directive) -> str:
        name = d.target
        if not name:
            return "用法：`/spawn <name> [cwd]`"
        cwd = d.args.get("cwd", "~")
        try:
            term = await self._manager.spawn(name, cwd=cwd)
        except TerminalError as e:
            return f"⚠️ {e}"
        self._default_target = name
        return f"✅ 已新建终端 `{term.name}`（cwd=`{cwd}`），并设为默认。"

    async def _do_kill(self, target: str | None) -> str:
        if not target:
            return "用法：`/kill <name>`"
        try:
            await self._manager.kill(target)
        except TerminalError as e:
            return f"⚠️ {e}"
        if self._default_target == target:
            self._default_target = None
        return f"🗑️ 已关闭终端 `{target}`。"

    async def _do_confirm(self, d: Directive) -> str:
        target = self._default_target
        if not target:
            return "⚠️ 没有默认终端可确认。"
        term = self._manager.get(target)
        if term is None:
            return f"⚠️ 终端 `{target}` 不存在。"
        answer = bool(d.args.get("answer"))
        # Claude permission prompts: "1" (yes) / "2"/Esc (no). We type the digit.
        await forwarder.forward(term, "1" if answer else "2")
        return f"{'✅ 已确认' if answer else '🚫 已拒绝'} `{target}` 的提示。"

    # -- help --------------------------------------------------------------
    def _help_text(self) -> str:
        return (
            "### 🧠 Hivemind 指令帮助\n"
            "| 指令 | 说明 |\n"
            "|------|------|\n"
            "| `@<name> <文本>` | 发给指定终端并设为默认 |\n"
            "| `<文本>` | 发给当前默认终端 |\n"
            "| `/ls` | 列出终端及状态 |\n"
            "| `/status [name]` | 查看终端最近输出 |\n"
            "| `/spawn <name> [cwd]` | 新建终端 |\n"
            "| `/kill <name>` | 关闭终端 |\n"
            "| `/y` `/n` | 回答确认提示 |\n"
            "| `/help` | 显示本帮助 |"
        )

    # -- accessors (for tests/monitor) ------------------------------------
    @property
    def default_target(self) -> str | None:
        return self._default_target
