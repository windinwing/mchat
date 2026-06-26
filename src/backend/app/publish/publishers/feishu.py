"""Feishu (Lark) publisher — custom-group robot webhook.

Two message shapes supported:
  - ``text``    : plain text (default, most robust).
  - ``card``    : interactive card with optional title + rich text body.

P2 will add the Open Platform tenant-access-token path for richer features
(chat list, image upload). For MVP the group-robot webhook needs no OAuth —
only the webhook URL and (optionally) its signing secret.

Reference: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import httpx

from app.publish.base import BasePublisher, PublishRequest, PublishResult

#: Feishu caps a single webhook message body well below this.
_MAX_TEXT_LEN = 30000


class FeishuPublisher(BasePublisher):
    provider_key = "feishu"
    capabilities = ("publish:text",)

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("webhook_url") or "").strip())

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        webhook_url = (config.get("webhook_url") or "").strip()
        secret = (config.get("secret") or "").strip()
        msg_type = (config.get("msg_type") or "text").strip().lower()

        body = self._build_body(msg_type, request)
        if secret:
            self._sign(body, secret)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(webhook_url, json=body)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="http_error",
                error_message=f"Feishu webhook request failed: {exc}",
            )

        # Feishu returns 200 with { "code": <non-zero>, "msg": ... } on logical errors.
        if data.get("code") not in (0, None):
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="feishu_api_error",
                error_message=str(data.get("msg") or data),
                raw=data,
            )

        return PublishResult(
            success=True,
            provider=self.provider_key,
            message="Feishu message delivered",
            raw=data,
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _build_body(msg_type: str, request: PublishRequest) -> dict[str, Any]:
        if msg_type == "card":
            elements: list[dict[str, Any]] = []
            if request.title:
                elements.append(
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": _truncate(request.content, _MAX_TEXT_LEN),
                        },
                    }
                )
            else:
                elements.append(
                    {
                        "tag": "div",
                        "text": {
                            "tag": "plain_text",
                            "content": _truncate(request.content, _MAX_TEXT_LEN),
                        },
                    }
                )
            return {
                "msg_type": "interactive",
                "card": {
                    "header": (
                        {
                            "title": {
                                "tag": "plain_text",
                                "content": request.title or "Notification",
                            }
                        }
                        if request.title
                        else None
                    ),
                    "elements": elements,
                },
            }

        # default: plain text
        return {
            "msg_type": "text",
            "content": {"text": _truncate(request.content, _MAX_TEXT_LEN)},
        }

    @staticmethod
    def _sign(body: dict[str, Any], secret: str) -> None:
        """Attach timestamp + HMAC-SHA256 signature (enables Feishu sign verification)."""
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
        ).digest()
        import base64

        sign = base64.b64encode(hmac_code).decode("utf-8")
        body["timestamp"] = timestamp
        body["sign"] = sign


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit]
