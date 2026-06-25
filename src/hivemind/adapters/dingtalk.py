"""DingTalk adapter — outbound Stream-mode client + Markdown replies/pushes.

Uses the official `dingtalk-stream` SDK. The connection is OUTBOUND only
(WebSocket to DingTalk), so no inbound ports are opened on the host — that is
what lets Hivemind run behind NAT / on a laptop.

Flow:
  * Incoming chat message  -> _ChatHandler.process -> on_message callback
  * The callback returns Markdown text, replied via reply_markdown.

Proactive push (M2):
  DingTalk gives every incoming message a temporary `session_webhook` URL that
  can be POSTed to for a while after the message. We remember the most recent
  webhook per conversation; the Monitor uses push_markdown() to notify the phone
  when a terminal finishes / needs confirmation, with no inbound trigger.

  Caveat: a session_webhook expires (~couple hours). If the user has not messaged
  recently, a push may 410/expire — that is expected and logged, not fatal. M3's
  hooks path and the user simply messaging again both refresh it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import aiohttp
import dingtalk_stream
from dingtalk_stream import AckMessage

from hivemind.config import Settings

log = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    """Normalized inbound chat message (decoupled from the SDK types)."""

    sender_id: str          # staffId of the sender (for whitelist, M4)
    sender_name: str
    text: str
    conversation_id: str
    session_webhook: str = ""
    webhook_expire_ms: int = 0
    raw: object = None       # original ChatbotMessage, for reply routing


# A handler takes an inbound message and returns the Markdown reply body.
OnMessage = Callable[[IncomingMessage], Awaitable[str]]

_REPLY_TITLE = "Hivemind"


@dataclass
class _Webhook:
    url: str
    expire_ms: int

    @property
    def alive(self) -> bool:
        # 0 expiry = unknown; treat as alive and let the POST decide.
        return self.expire_ms == 0 or self.expire_ms > int(time.time() * 1000)


class WebhookRegistry:
    """Remembers the freshest session_webhook overall and per conversation."""

    def __init__(self) -> None:
        self._by_conv: dict[str, _Webhook] = {}
        self._latest: _Webhook | None = None

    def remember(self, conversation_id: str, url: str, expire_ms: int) -> None:
        if not url:
            return
        wh = _Webhook(url=url, expire_ms=expire_ms)
        if conversation_id:
            self._by_conv[conversation_id] = wh
        self._latest = wh

    def resolve(self, conversation_id: str | None) -> str | None:
        """Pick a live webhook: the named conversation's, else the latest."""
        if conversation_id and (wh := self._by_conv.get(conversation_id)) and wh.alive:
            return wh.url
        if self._latest and self._latest.alive:
            return self._latest.url
        return None


class _ChatHandler(dingtalk_stream.ChatbotHandler):
    """Bridges the SDK callback into our async on_message and replies Markdown."""

    def __init__(
        self,
        on_message: OnMessage,
        webhooks: WebhookRegistry,
        logger: logging.Logger,
    ) -> None:
        super().__init__()
        self.logger = logger
        self._on_message = on_message
        self._webhooks = webhooks

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        incoming = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        msg = IncomingMessage(
            sender_id=getattr(incoming, "sender_staff_id", "") or "",
            sender_name=getattr(incoming, "sender_nick", "") or "",
            text=(incoming.text.content if incoming.text else "").strip(),
            conversation_id=getattr(incoming, "conversation_id", "") or "",
            session_webhook=getattr(incoming, "session_webhook", "") or "",
            webhook_expire_ms=int(getattr(incoming, "session_webhook_expired_time", 0) or 0),
            raw=incoming,
        )
        # Capture the webhook so the Monitor can push to this conversation later.
        self._webhooks.remember(msg.conversation_id, msg.session_webhook, msg.webhook_expire_ms)
        try:
            reply = await self._on_message(msg)
        except Exception:  # never let a handler error kill the WS loop
            log.exception("on_message failed for sender=%s", msg.sender_id)
            reply = "⚠️ Hivemind 内部错误，请查看日志。"
        if reply:
            self.reply_markdown(_REPLY_TITLE, reply, incoming)
        return AckMessage.STATUS_OK, "OK"


class DingTalkClient:
    """Owns the Stream client lifecycle and proactive push."""

    def __init__(self, settings: Settings, on_message: OnMessage) -> None:
        self._settings = settings
        self._on_message = on_message
        self._client: dingtalk_stream.DingTalkStreamClient | None = None
        self._webhooks = WebhookRegistry()

    def _build(self) -> dingtalk_stream.DingTalkStreamClient:
        dt = self._settings.dingtalk
        if not dt.client_id or not dt.client_secret:
            raise RuntimeError(
                "DingTalk credentials missing: set HIVEMIND_DINGTALK__CLIENT_ID "
                "and HIVEMIND_DINGTALK__CLIENT_SECRET in .env"
            )
        credential = dingtalk_stream.Credential(dt.client_id, dt.client_secret)
        client = dingtalk_stream.DingTalkStreamClient(credential)
        handler = _ChatHandler(self._on_message, self._webhooks, log)
        client.register_callback_handler(
            dingtalk_stream.chatbot.ChatbotMessage.TOPIC, handler
        )
        return client

    async def start(self) -> None:
        """Connect and run the receive loop until cancelled.

        The SDK's `start()` integrates with the current asyncio loop; the Bridge
        wraps this in a reconnect supervisor (see bridge.py).
        """
        self._client = self._build()
        log.info("DingTalk Stream client connecting...")
        await self._client.start()

    async def push_markdown(
        self, title: str, text: str, conversation_id: str | None = None
    ) -> bool:
        """Proactively send a Markdown card via a remembered session_webhook.

        Returns True on success. Returns False (and logs) when no live webhook is
        known yet — e.g. the user has not messaged the bot since startup.
        """
        url = self._webhooks.resolve(conversation_id)
        if not url:
            log.warning("push skipped: no live session_webhook yet (user must DM the bot once)")
            return False
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
        }
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        log.warning("push failed: HTTP %s %s", resp.status, body[:200])
                        return False
            return True
        except Exception:
            log.exception("push_markdown failed")
            return False
