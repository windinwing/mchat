"""WeChat Work (企业微信) publisher — group robot webhook.

Posts a text (or markdown) message to a WeChat Work group via a group robot's
webhook key. Same simple webhook shape as Feishu/DingTalk.

Reference: https://developer.work.weixin.qq.com/document/path/91770
"""

from __future__ import annotations

from typing import Any

import httpx

from app.publish.base import BasePublisher, PublishRequest, PublishResult

_MAX_TEXT_LEN = 2048  # WeChat Work text cap per message


class WeComPublisher(BasePublisher):
    provider_key = "wecom"
    capabilities = ("publish:text",)

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("webhook_url") or config.get("key") or "").strip())

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        webhook_url = (config.get("webhook_url") or "").strip()
        # Allow passing just the robot key -> build the canonical URL.
        if not webhook_url:
            key = (config.get("key") or "").strip()
            webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
        msg_type = (config.get("msg_type") or "text").strip().lower()

        body = self._build_body(msg_type, request)

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
                error_message=f"WeCom webhook request failed: {exc}",
            )

        # WeCom returns {"errcode": 0, "errmsg": "ok"}.
        if data.get("errcode") not in (0, None):
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="wecom_api_error",
                error_message=str(data.get("errmsg") or data),
                raw=data,
            )

        return PublishResult(
            success=True,
            provider=self.provider_key,
            message="WeCom message delivered",
            raw=data,
        )

    @staticmethod
    def _build_body(msg_type: str, request: PublishRequest) -> dict[str, Any]:
        text = _truncate(request.content, _MAX_TEXT_LEN)
        if msg_type == "markdown":
            return {"msgtype": "markdown", "markdown": {"content": text}}
        return {"msgtype": "text", "text": {"content": text}}


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit]
