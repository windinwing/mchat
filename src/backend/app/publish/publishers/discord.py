"""Discord publisher — incoming webhook.

Posts a message to a Discord channel via a webhook URL. Text + optional
username override. Simplest overseas channel.

Reference: https://discord.com/developers/docs/resources/webhook
"""

from __future__ import annotations

from typing import Any

import httpx

from app.publish.base import BasePublisher, PublishRequest, PublishResult

_MAX_TEXT_LEN = 2000  # Discord message cap


class DiscordPublisher(BasePublisher):
    provider_key = "discord"
    capabilities = ("publish:text",)

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("webhook_url") or "").strip())

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        webhook_url = (config.get("webhook_url") or "").strip()
        text = _truncate(request.content, _MAX_TEXT_LEN)
        if request.title:
            text = f"**{request.title}**\n{text}"

        payload: dict[str, Any] = {"content": text}
        username = (config.get("username") or "").strip()
        if username:
            payload["username"] = username

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(webhook_url, json=payload)
                # Discord returns 204 No Content on success (empty body).
                if resp.status_code == 204:
                    return PublishResult(
                        success=True,
                        provider=self.provider_key,
                        message="Discord message delivered",
                    )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="http_error",
                error_message=f"Discord webhook request failed: {exc}",
            )

        # Non-204 with JSON → error payload.
        if isinstance(data, dict) and data.get("code") not in (None, 0):
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="discord_api_error",
                error_message=str(data.get("message") or data),
                raw=data,
            )

        return PublishResult(
            success=True,
            provider=self.provider_key,
            message="Discord message delivered",
        )


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit]
