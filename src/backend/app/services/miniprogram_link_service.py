"""WeChat mini program URL Link + scheme parsing (chat / H5 jump)."""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx
from loguru import logger

from app.core.config import settings

_SCHEME_RE = re.compile(r"weixin://dl/business/\?[^\s\])<>\"']+")

_MP_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_URL_LINK_CACHE: dict[str, tuple[str, float]] = {}


def parse_weixin_business_scheme(url: str) -> dict[str, str]:
    raw = (url or "").strip()
    if not raw.startswith("weixin://dl/business/"):
        return {}
    try:
        parsed = urlparse(raw.replace("weixin://", "https://", 1))
        qs = parse_qs(parsed.query)
        appid = (qs.get("appid") or [""])[0].strip()
        path = (qs.get("path") or [""])[0].strip().lstrip("/")
        query = (qs.get("query") or [""])[0].strip()
        env_version = (qs.get("env_version") or ["release"])[0].strip() or "release"
        if not appid:
            return {}
        return {
            "appid": appid,
            "path": path or "pages/index/index",
            "query": query,
            "env_version": env_version,
        }
    except Exception:
        return {}


def _mp_credentials(appid: str | None = None) -> tuple[str, str] | None:
    cfg_app = (settings.miniprogram_jump_app_id or "").strip()
    cfg_secret = (settings.miniprogram_jump_app_secret or "").strip()
    if cfg_app and cfg_secret and (not appid or appid == cfg_app):
        return cfg_app, cfg_secret
    return None


async def _fetch_mp_access_token(app_id: str, app_secret: str) -> str:
    now = time.time()
    cached = _MP_TOKEN_CACHE.get(app_id)
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
        raise RuntimeError(f"miniprogram token failed: {data}")
    token = str(data.get("access_token") or "").strip()
    expires = int(data.get("expires_in") or 7200)
    if not token:
        raise RuntimeError("miniprogram token missing access_token")
    _MP_TOKEN_CACHE[app_id] = (token, now + max(300, expires - 120))
    return token


async def generate_url_link(
    *,
    app_id: str,
    app_secret: str,
    path: str,
    query: str = "",
    env_version: str = "release",
) -> str | None:
    """Return https://wxaurl.cn/... when API credentials are valid."""
    cache_key = f"{app_id}:{path}:{query}:{env_version}"
    now = time.time()
    cached = _URL_LINK_CACHE.get(cache_key)
    if cached and cached[1] > now:
        return cached[0]

    token = await _fetch_mp_access_token(app_id, app_secret)
    payload: dict[str, object] = {
        "path": path if path.startswith("/") else f"/{path}",
        "env_version": env_version or "release",
        "is_expire": True,
        "expire_type": 1,
        "expire_interval": 30,
    }
    if query:
        payload["query"] = query

    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.post(
            "https://api.weixin.qq.com/wxa/generate_urllink",
            params={"access_token": token},
            json=payload,
        )
        data = resp.json()
    if int(data.get("errcode", 0) or 0) != 0:
        logger.warning("generate_urllink failed for {}: {}", app_id, data)
        return None
    link = str(data.get("url_link") or "").strip()
    if not link:
        return None
    _URL_LINK_CACHE[cache_key] = (link, now + 29 * 86400)
    return link


async def resolve_miniprogram_click_url(
    weixin_url: str,
    *,
    label: str = "",
) -> str:
    """Prefer URL Link (works in WeChat chat); fallback to H5 bridge."""
    from app.utils.wechat_miniprogram import mini_program_bridge_url

    parsed = parse_weixin_business_scheme(weixin_url)
    if not parsed:
        return weixin_url

    creds = _mp_credentials(parsed.get("appid"))
    if creds:
        app_id, app_secret = creds
        try:
            link = await generate_url_link(
                app_id=app_id,
                app_secret=app_secret,
                path=parsed["path"],
                query=parsed.get("query") or "",
                env_version=parsed.get("env_version") or "release",
            )
            if link:
                return link
        except Exception as e:
            logger.warning("URL Link generation failed: {}", e)

    return mini_program_bridge_url(weixin_url, label=label)


async def rewrite_miniprogram_links_async(text: str) -> str:
    """Replace weixin:// markdown links with URL Link or HTTPS bridge."""
    from app.utils.wechat_miniprogram import _MARKDOWN_LINK_RE

    async def _repl_md(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2).strip()
        if url.startswith("weixin://dl/business/"):
            resolved = await resolve_miniprogram_click_url(url, label=label)
            if resolved.startswith("http"):
                return f"[{label}]({resolved})"
            return f"{label} {resolved}"
        return match.group(0)

    updated = text or ""
    parts: list[str] = []
    last = 0
    for match in _MARKDOWN_LINK_RE.finditer(updated):
        parts.append(updated[last : match.start()])
        parts.append(await _repl_md(match))
        last = match.end()
    parts.append(updated[last:])
    updated = "".join(parts)

    if "weixin://dl/business/" not in updated:
        return updated

    out: list[str] = []
    last = 0
    for match in _SCHEME_RE.finditer(updated):
        out.append(updated[last : match.start()])
        raw = match.group(0)
        resolved = await resolve_miniprogram_click_url(raw)
        out.append(resolved)
        last = match.end()
    out.append(updated[last:])
    return "".join(out)
