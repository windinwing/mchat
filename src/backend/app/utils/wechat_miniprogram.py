"""WeChat mini program URL Scheme helpers for OA / H5 bridge links."""

from __future__ import annotations

import re
from urllib.parse import quote

from app.core.config import settings

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_WEIXIN_MP_SCHEME_RE = re.compile(r"weixin://dl/business/\?[^\s\])<>\"']+")


def mini_program_bridge_url(weixin_url: str, *, label: str = "") -> str:
    """Map weixin:// scheme to public H5 bridge (clickable inside WeChat chat)."""
    base = (settings.mchat_public_base_url or "").strip().rstrip("/")
    if not base:
        return weixin_url
    name = quote((label or "微信小程序").strip() or "微信小程序")
    encoded = quote(weixin_url.strip(), safe="")
    return f"{base}/mini-program?url={encoded}&name={name}"


def rewrite_miniprogram_links(text: str) -> str:
    """Replace markdown weixin:// links with HTTPS bridge URLs."""

    def _repl_md(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2).strip()
        if url.startswith("weixin://dl/business/"):
            return f"[{label}]({mini_program_bridge_url(url, label=label)})"
        return match.group(0)

    updated = _MARKDOWN_LINK_RE.sub(_repl_md, text or "")
    if "weixin://dl/business/" not in updated:
        return updated

    def _repl_plain(match: re.Match[str]) -> str:
        raw = match.group(0)
        return mini_program_bridge_url(raw)

    return _WEIXIN_MP_SCHEME_RE.sub(_repl_plain, updated)
