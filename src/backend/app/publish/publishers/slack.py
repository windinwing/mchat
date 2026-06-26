"""Slack publisher — incoming webhook.

Posts a message to a Slack channel via a custom incoming webhook URL. Text-only
for MVP; rich blocks / file upload are P3.

Reference: https://api.slack.com/messaging/webhooks
"""

from __future__ import annotations

from typing import Any

import httpx

from app.publish.base import BasePublisher, PublishRequest, PublishResult

_MAX_TEXT_LEN = 40000  # Slack allows ~40k per message


class SlackPublisher(BasePublisher):
    provider_key = "slack"
    capabilities = ("publish:text",)

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("webhook_url") or "").strip())

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        webhook_url = (config.get("webhook_url") or "").strip()
        text = _truncate(request.content, _MAX_TEXT_LEN)
        if request.title:
            text = f"*{request.title}*\n{text}"

        payload: dict[str, Any] = {"text": text}
        # Optional named bot persona
        username = (config.get("username") or "").strip()
        if username:
            payload["username"] = username

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(webhook_url, json=payload)
                resp.raise_for_status()
                body = resp.text.strip()
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="http_error",
                error_message=f"Slack webhook request failed: {exc}",
            )

        # Slack returns "ok" on success, JSON error otherwise.
        if body and body != "ok":
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="slack_api_error",
                error_message=body[:300],
                raw={"response": body},
            )

        return PublishResult(
            success=True,
            provider=self.provider_key,
            message="Slack message delivered",
        )


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit]
