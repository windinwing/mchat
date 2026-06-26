"""Facebook publisher — Graph API.

Posts to a Facebook Page (not a personal profile — personal posting via API was
deprecated). Requires a Page Access Token with pages_manage_posts permission
and the target page_id.

Reference: https://developers.facebook.com/docs/pages-api/posts
"""

from __future__ import annotations

from typing import Any

import httpx

from app.publish.base import BasePublisher, PublishRequest, PublishResult

_GRAPH = "https://graph.facebook.com/v19.0"


class FacebookPublisher(BasePublisher):
    provider_key = "facebook"
    capabilities = ("publish:text",)

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("page_id") or "").strip()) and bool(
            (config.get("page_access_token") or "").strip()
        )

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        page_id = (config.get("page_id") or "").strip()
        token = (config.get("page_access_token") or "").strip()

        message = request.content or ""
        if request.title:
            message = f"{request.title}\n\n{message}"

        params: dict[str, Any] = {"message": message, "access_token": token}
        # Optional link attachment.
        link = (config.get("link") or "").strip()
        if link:
            params["link"] = link

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{_GRAPH}/{page_id}/feed", params=params
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="http_error",
                error_message=f"Facebook Graph API request failed: {exc}",
            )

        post_id = str(data.get("id") or "")
        if not post_id or "error" in data:
            err = (data.get("error") or {}).get("message") if isinstance(data, dict) else None
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="api_error",
                error_message=str(err or data),
                raw=data,
            )
        return PublishResult(
            success=True,
            provider=self.provider_key,
            message="Facebook post published",
            remote_id=post_id,
            remote_url=f"https://www.facebook.com/{post_id.replace('_', '/posts/')}",
        )
