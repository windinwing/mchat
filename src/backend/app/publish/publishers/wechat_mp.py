"""WeChat Official Account (微信公众号) publisher.

Posts an article draft via the official API. This is the most involved API
channel because it requires:
  1. stable access_token (app_id + app_secret) — cached with expiry
  2. upload a thumb image as material (media/uploadimg) for the cover
  3. create a draft (draft/add) with title + content + thumb_media_id
  4. (optional) publish the draft (freepublish/submit) for mass send

Requires an authenticated 服务号/订阅号 with draft+publish permissions.

Reference:
  - https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Get_access_token.html
  - https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.publish.base import BasePublisher, PublishMedia, PublishRequest, PublishResult

_BASE = "https://api.weixin.qq.com/cgi-bin"

# Module-level access_token cache keyed by app_id → (token, expires_at).
_token_cache: dict[str, tuple[str, float]] = {}


class WechatMpPublisher(BasePublisher):
    provider_key = "wechat_mp"
    capabilities = ("publish:text",)

    async def validate_config(self, config: dict[str, Any]) -> bool:
        return bool((config.get("app_id") or "").strip()) and bool(
            (config.get("app_secret") or "").strip()
        )

    async def publish(
        self, config: dict[str, Any], request: PublishRequest
    ) -> PublishResult:
        app_id = (config.get("app_id") or "").strip()
        app_secret = (config.get("app_secret") or "").strip()
        publish_now = bool(config.get("publish_now", True))

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                token = await _get_access_token(client, app_id, app_secret)
            except Exception as exc:
                return PublishResult(
                    success=False,
                    provider=self.provider_key,
                    error_code="token_error",
                    error_message=f"获取 access_token 失败: {exc}",
                )

            # 1. Upload a cover image (required for a draft). Use first media.
            thumb_media_id = await self._upload_thumb(client, token, request)
            if thumb_media_id is None:
                return PublishResult(
                    success=False,
                    provider=self.provider_key,
                    error_code="thumb_error",
                    error_message="公众号草稿需要封面图，请提供 media 图片",
                )

            # 2. Create draft.
            try:
                media_id = await self._add_draft(
                    client, token, request, thumb_media_id
                )
            except Exception as exc:
                return PublishResult(
                    success=False,
                    provider=self.provider_key,
                    error_code="draft_error",
                    error_message=f"创建草稿失败: {exc}",
                )

            # 3. Optionally publish (mass send) — needs extra permission.
            if publish_now:
                try:
                    await self._publish_draft(client, token, media_id)
                    return PublishResult(
                        success=True,
                        provider=self.provider_key,
                        message="公众号草稿已创建并发布",
                        remote_id=media_id,
                    )
                except Exception as exc:
                    # Draft created but publish failed — still partial success.
                    return PublishResult(
                        success=True,
                        provider=self.provider_key,
                        message=f"草稿已创建(media_id={media_id})，但发布失败: {exc}",
                        remote_id=media_id,
                        error_code="publish_warning",
                    )

            return PublishResult(
                success=True,
                provider=self.provider_key,
                message="公众号草稿已创建（未发布）",
                remote_id=media_id,
            )

    async def _upload_thumb(
        self, client: httpx.AsyncClient, token: str, request: PublishRequest
    ) -> str | None:
        # WeChat's uploadimg returns a url + media_id for use in articles.
        media = next((m for m in request.media if m.type == "image" and m.url), None)
        if media is None:
            return None
        url = f"{_BASE}/media/uploadimg?access_token={token}"
        # Fetch the image bytes, then upload as multipart.
        try:
            img_resp = await client.get(media.url)  # type: ignore[arg-type]
            img_resp.raise_for_status()
        except Exception:
            return None
        files = {"media": ("cover.jpg", img_resp.content, "image/jpeg")}
        resp = await client.post(url, files=files)
        data = resp.json()
        return str(data.get("media_id") or "") or None

    async def _add_draft(
        self,
        client: httpx.AsyncClient,
        token: str,
        request: PublishRequest,
        thumb_media_id: str,
    ) -> str:
        url = f"{_BASE}/draft/add?access_token={token}"
        # Wrap content in minimal HTML paragraphs.
        body_text = request.content or ""
        html_content = "".join(f"<p>{line}</p>" for line in body_text.split("\n") if line.strip())
        article = {
            "title": (request.title or "Notification")[:64],
            "author": "MChat",
            "content": html_content or "<p></p>",
            "thumb_media_id": thumb_media_id,
            "content_source_url": "",
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }
        resp = await client.post(url, json={"articles": [article]})
        data = resp.json()
        if data.get("errcode") not in (0, None):
            raise RuntimeError(str(data.get("errmsg") or data))
        return str(data.get("media_id"))

    async def _publish_draft(
        self, client: httpx.AsyncClient, token: str, media_id: str
    ) -> None:
        url = f"{_BASE}/freepublish/submit?access_token={token}"
        resp = await client.post(url, json={"media_id": media_id})
        data = resp.json()
        if data.get("errcode") not in (0, None):
            raise RuntimeError(str(data.get("errmsg") or data))


async def _get_access_token(
    client: httpx.AsyncClient, app_id: str, app_secret: str
) -> str:
    """Fetch (and cache) the stable access_token for the app."""
    cached = _token_cache.get(app_id)
    now = time.time()
    if cached and cached[1] > now + 60:  # 60s safety margin
        return cached[0]
    url = (
        f"{_BASE}/token?grant_type=client_credential"
        f"&appid={app_id}&secret={app_secret}"
    )
    resp = await client.get(url)
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(str(data.get("errmsg") or data))
    expires_in = int(data.get("expires_in") or 7200)
    _token_cache[app_id] = (token, now + expires_in)
    return token
