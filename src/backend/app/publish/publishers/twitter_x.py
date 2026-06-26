"""X (Twitter) publisher — API v2.

Posts a tweet via the X API v2 using OAuth 2.0 user-context tokens (the token
must have tweet.write scope). Requires a refresh_token + client credentials to
mint a fresh access_token, OR a pre-supplied access_token.

Reference: https://developer.x.com/en/docs/x-api/tweet-management
"""

from __future__ import annotations

from typing import Any

import httpx

from app.publish.base import BasePublisher, PublishRequest, PublishResult

_API = "https://api.x.com/2"
_AUTH = "https://api.x.com/2/oauth2/token"
_MAX_TEXT_LEN = 280  # default; Premium allows more


class TwitterXPublisher(BasePublisher):
    provider_key = "twitter_x"
    capabilities = ("publish:text",)

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("access_token") or "").strip()) or (
            bool((config.get("client_id") or "").strip())
            and bool((config.get("refresh_token") or "").strip())
        )

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        access_token = await self._resolve_token(config)
        if access_token is None:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="auth_error",
                error_message="无法获取 X access_token（需 access_token 或 client_id+refresh_token）",
            )

        text = (request.content or "")[:_MAX_TEXT_LEN]
        if request.title:
            text = f"{request.title}\n{text}"[:_MAX_TEXT_LEN]

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{_API}/tweets",
                    json={"text": text},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="http_error",
                error_message=f"X API request failed: {exc}",
            )

        tweet_id = str((data.get("data") or {}).get("id") or "")
        if not tweet_id:
            return PublishResult(
                success=False,
                provider=self.provider_key,
                error_code="api_error",
                error_message=str(data.get("detail") or data),
                raw=data,
            )
        return PublishResult(
            success=True,
            provider=self.provider_key,
            message="Tweet posted",
            remote_id=tweet_id,
            remote_url=f"https://x.com/i/web/status/{tweet_id}",
        )

    async def _resolve_token(self, config: dict[str, Any]) -> str | None:
        # Direct access_token takes precedence.
        direct = (config.get("access_token") or "").strip()
        if direct:
            return direct
        # Otherwise refresh via OAuth2 client.
        client_id = (config.get("client_id") or "").strip()
        refresh_token = (config.get("refresh_token") or "").strip()
        client_secret = (config.get("client_secret") or "").strip()
        if not (client_id and refresh_token):
            return None
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _AUTH,
                data={
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                },
                auth=(client_id, client_secret) if client_secret else None,
            )
            data = resp.json()
        return str(data.get("access_token") or "") or None
