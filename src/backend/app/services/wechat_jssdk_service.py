"""WeChat Official Account JS-SDK signature (wx-open-launch-weapp on H5)."""

from __future__ import annotations

import hashlib
import secrets
import time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.channel import Channel

_TICKET_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


async def _oa_credentials(db: AsyncSession | None) -> tuple[str, str] | None:
    app_id = (settings.wechat_jssdk_app_id or "").strip()
    app_secret = (settings.wechat_jssdk_app_secret or "").strip()
    if app_id and app_secret:
        return app_id, app_secret
    if db is None:
        return None
    result = await db.execute(
        select(Channel).where(
            Channel.channel_type == "wechat",
            Channel.enabled.is_(True),
        )
    )
    for ch in result.scalars().all():
        cfg = ch.config or {}
        cid = str(cfg.get("app_id") or "").strip()
        secret = str(cfg.get("app_secret") or "").strip()
        if cid and secret:
            return cid, secret
    return None


async def _fetch_access_token(app_id: str, app_secret: str) -> str:
    now = time.time()
    cached = _TOKEN_CACHE.get(app_id)
    if cached and cached[1] > now + 120:
        return cached[0]
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": app_id,
                "secret": app_secret,
            },
        )
        data = resp.json()
    if int(data.get("errcode", 0) or 0) != 0:
        raise RuntimeError(f"OA access_token failed: {data}")
    token = str(data.get("access_token") or "").strip()
    expires = int(data.get("expires_in") or 7200)
    if not token:
        raise RuntimeError("OA access_token missing")
    _TOKEN_CACHE[app_id] = (token, now + max(300, expires - 120))
    return token


async def _fetch_jsapi_ticket(app_id: str, app_secret: str) -> str:
    now = time.time()
    cached = _TICKET_CACHE.get(app_id)
    if cached and cached[1] > now + 120:
        return cached[0]
    token = await _fetch_access_token(app_id, app_secret)
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/cgi-bin/ticket/getticket",
            params={"access_token": token, "type": "jsapi"},
        )
        data = resp.json()
    if int(data.get("errcode", 0) or 0) != 0:
        raise RuntimeError(f"jsapi_ticket failed: {data}")
    ticket = str(data.get("ticket") or "").strip()
    expires = int(data.get("expires_in") or 7200)
    if not ticket:
        raise RuntimeError("jsapi_ticket missing")
    _TICKET_CACHE[app_id] = (ticket, now + max(300, expires - 120))
    return ticket


def _sign_ticket(ticket: str, url: str) -> dict[str, str | int]:
    nonce = secrets.token_hex(8)
    timestamp = int(time.time())
    raw = (
        f"jsapi_ticket={ticket}&noncestr={nonce}&timestamp={timestamp}&url={url}"
    )
    signature = hashlib.sha1(raw.encode()).hexdigest()
    return {
        "nonceStr": nonce,
        "timestamp": timestamp,
        "signature": signature,
    }


async def build_jssdk_config(db: AsyncSession | None, page_url: str) -> dict:
    creds = await _oa_credentials(db)
    if not creds:
        raise RuntimeError("WeChat OA credentials not configured for JS-SDK")
    app_id, app_secret = creds
    ticket = await _fetch_jsapi_ticket(app_id, app_secret)
    signed = _sign_ticket(ticket, page_url.split("#")[0])
    return {
        "appId": app_id,
        "nonceStr": signed["nonceStr"],
        "timestamp": signed["timestamp"],
        "signature": signed["signature"],
    }
