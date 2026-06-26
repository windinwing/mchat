"""DingTalk (钉钉) publisher — custom group robot webhook.

Posts a text (or markdown) message to a DingTalk group via a custom robot's
outgoing webhook. Simplest channel — same shape as Feishu/Slack.

Reference: https://open.dingtalk.com/document/robots/custom-robot-access
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
from typing import Any

import httpx

from app.publish.base import BasePublisher, PublishRequest, PublishResult

_MAX_TEXT_LEN = 20000


class DingTalkPublisher(BasePublisher):
    provider_key = "dingtalk"
    capabilities = ("publish:text",)

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("webhook_url") or "").strip())

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        webhook_url = (config.get("webhook_url") or "").strip()
        secret = (config.get("secret") or "").strip()
        msg_type = (config.get("msg_type") or "text").strip().lower()

        # DingTalk sign verification appends timestamp&sign to the URL.
        url = self._sign_url(webhook_url, secret) if secret else webhook_url
        body = self._build_body(msg_type, request)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="http_error",
                error_message=f"DingTalk webhook request failed: {exc}",
            )

        # DingTalk returns {"errcode": 0, "errmsg": "ok"} on success.
        if data.get("errcode") not in (0, None):
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="dingtalk_api_error",
                error_message=str(data.get("errmsg") or data),
                raw=data,
            )

        return PublishResult(
            success=True,
            provider=self.provider_key,
            message="DingTalk message delivered",
            raw=data,
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _build_body(msg_type: str, request: PublishRequest) -> dict[str, Any]:
        text = _truncate(request.content, _MAX_TEXT_LEN)
        if msg_type == "markdown":
            title = request.title or "Notification"
            return {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": text},
            }
        # default: text
        return {"msgtype": "text", "text": {"content": text}}

    @staticmethod
    def _sign_url(webhook_url: str, secret: str) -> str:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        sep = "&" if "?" in webhook_url else "?"
        return f"{webhook_url}{sep}timestamp={timestamp}&sign={sign}"


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit]
