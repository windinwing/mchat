"""LinkedIn publisher — UGC Posts API.

Posts a text share to the authenticated member's feed (or an organization page)
via the UGC Posts API. Requires an OAuth2 access token (profile + w_member_social
scope) and the actor's person URN (urn:li:person:...) or org URN.

Reference: https://learn.microsoft.com/linkedin/marketing/integrations/community-management/shares/ugc-post-api
"""

from __future__ import annotations

from typing import Any

import httpx

from app.publish.base import BasePublisher, PublishRequest, PublishResult

_API = "https://api.linkedin.com/v2/ugcPosts"
_MAX_TEXT_LEN = 3000


class LinkedInPublisher(BasePublisher):
    provider_key = "linkedin"
    capabilities = ("publish:text",)

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("access_token") or "").strip()) and bool(
            (config.get("author_urn") or "").strip()
        )

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        token = (config.get("access_token") or "").strip()
        author = (config.get("author_urn") or "").strip()
        # author e.g. "urn:li:person:XXX" or "urn:li:organization:123"

        text = (request.content or "")[:_MAX_TEXT_LEN]
        if request.title:
            text = f"{request.title}\n\n{text}"[:_MAX_TEXT_LEN]

        body = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    _API,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Restli-Protocol-Version": "2.0.0",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="http_error",
                error_message=f"LinkedIn API request failed: {exc}",
            )

        post_urn = str(data.get("id") or "")
        if not post_urn:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="api_error",
                error_message=str(data.get("message") or data),
                raw=data,
            )
        return PublishResult(
            success=True,
            provider=self.provider_key,
            message="LinkedIn post published",
            remote_id=post_urn,
        )
