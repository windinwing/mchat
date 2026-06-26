"""Telegram publisher — bot posts to a channel.

Uses a bot token to send a message to a channel (the bot must be an admin of
the target channel). Mirrors the inbound TelegramAdapter but outbound.

Reference: https://core.telegram.org/bots/api#sendmessage
"""

from __future__ import annotations

from typing import Any

import httpx

from app.publish.base import BasePublisher, PublishRequest, PublishResult

_MAX_TEXT_LEN = 4096  # Telegram hard limit per message


class TelegramChannelPublisher(BasePublisher):
    provider_key = "telegram_channel"
    capabilities = ("publish:text",)

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("bot_token") or "").strip()) and bool(
            (config.get("chat_id") or config.get("channel") or "").strip()
        )

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        token = (config.get("bot_token") or "").strip()
        chat_id = str(config.get("chat_id") or config.get("channel") or "").strip()
        text = _truncate(request.content, _MAX_TEXT_LEN)
        if request.title:
            text = f"*{request.title}*\n{text}"

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="http_error",
                error_message=f"Telegram request failed: {exc}",
            )

        if not data.get("ok"):
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="telegram_api_error",
                error_message=str(data.get("description") or data),
                raw=data,
            )

        msg = (data.get("result") or {}).get("message_id")
        return PublishResult(
            success=True,
            provider=self.provider_key,
            message="Telegram message delivered",
            remote_id=str(msg) if msg is not None else None,
            raw=data,
        )


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit]
