"""Normalize message assets into a single outbound_assets structure."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, unquote

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_MARKDOWN_UPLOAD_LINK_RE = re.compile(r"\[([^\]]+)\]\((/uploads/[^)\s]+)\)")
_URL_RE = re.compile(r'(?<!\()\bhttps?://[^\s<>"]+')
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}

# LLM-invented download URLs (not produced by skill export pipeline).
_HALLUCINATED_FILE_URL_RE = re.compile(
    r"^https?://(?:www\.)?mchat\.com/files/",
    re.I,
)
_HALLUCINATED_UUID_FILE_RE = re.compile(
    r"^https?://[^/]+/files/[a-f0-9-]{36}\.[a-z0-9]+$",
    re.I,
)
_BOGUS_MARKDOWN_FILE_LINK_RE = re.compile(
    r"\[([^\]]*)\]\((?:https?://[^/]+)?/files/[a-f0-9-]{36}\.[a-z0-9]+[^)]*\)",
    re.I,
)
_BOGUS_RAW_FILE_URL_RE = re.compile(
    r"https?://(?:www\.)?mchat\.com/files/\S+",
    re.I,
)
_BOGUS_ARROW_DOWNLOAD_RE = re.compile(
    r"[📄📥]?\s*[^\n→\[]*\.xlsx\s*→\s*点击下载",
    re.I,
)
_FAKE_EXPORT_LINE_MARKERS = (
    "下载链接已生成",
    "请您点击链接下载",
    "如果仍然无法下载",
    "更换浏览器",
    "邮箱",
    "发送到邮箱",
    "还需要其他帮助",
)
_FAKE_XLSX_ARROW_LINE_RE = re.compile(r"\.xlsx\s*→", re.I)


def is_hallucinated_download_url(url: str) -> bool:
    """True for LLM-fabricated file URLs that should not be shown or collected."""
    u = (url or "").strip()
    if not u:
        return False
    if u.startswith("/files/") and "/uploads/" not in u:
        return True
    if _HALLUCINATED_FILE_URL_RE.match(u):
        return True
    if _HALLUCINATED_UUID_FILE_RE.match(u):
        return True
    return False


def sanitize_hallucinated_download_urls(text: str) -> str:
    """Strip bogus download links from assistant markdown before persist/display."""
    if not text:
        return text
    cleaned = _BOGUS_MARKDOWN_FILE_LINK_RE.sub("", text)
    cleaned = _BOGUS_RAW_FILE_URL_RE.sub("", cleaned)
    cleaned = _BOGUS_ARROW_DOWNLOAD_RE.sub("", cleaned)
    if "/uploads/" not in text:
        kept_lines: list[str] = []
        for line in cleaned.splitlines():
            if any(marker in line for marker in _FAKE_EXPORT_LINE_MARKERS):
                continue
            if _FAKE_XLSX_ARROW_LINE_RE.search(line) and "/uploads/" not in line:
                continue
            kept_lines.append(line)
        cleaned = "\n".join(kept_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def has_upload_file_assets(assets: list[dict] | None) -> bool:
    """True when tool/extra payload already contains a real uploaded file URL."""
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        url = str(asset.get("url") or "").strip()
        if url.startswith("/uploads/"):
            return True
    return False


def _basename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name.strip()
    return name or "link"


def _infer_asset_type(
    asset_type: str | None,
    mime: str | None,
    url: str,
) -> str:
    normalized = (asset_type or "").strip().lower()
    if normalized in {"image", "file", "link"}:
        return normalized

    mime_value = (mime or "").strip().lower()
    if mime_value.startswith("image/"):
        return "image"

    ext = Path(urlparse(url).path).suffix.lower()
    if ext in _IMAGE_EXTENSIONS:
        return "image"
    if ext:
        return "file"
    return "link"


def normalize_outbound_asset(
    asset: object,
    *,
    default_source: str,
) -> dict | None:
    if not isinstance(asset, dict):
        return None

    url = str(asset.get("url") or "").strip()
    if not url:
        return None

    mime = str(asset.get("mime") or "").strip() or None
    asset_type = _infer_asset_type(str(asset.get("type") or ""), mime, url)
    name = str(asset.get("name") or asset.get("title") or "").strip()
    if not name:
        name = _basename_from_url(url)

    normalized = {
        "type": asset_type,
        "name": name,
        "url": url,
        "source": str(asset.get("source") or default_source).strip() or default_source,
    }
    if mime:
        normalized["mime"] = mime

    title = str(asset.get("title") or "").strip()
    if title and title != name:
        normalized["title"] = title

    return normalized


def extract_content_assets(content: str) -> list[dict]:
    """Extract markdown links and raw URLs from assistant text."""
    text = content or ""
    assets: list[dict] = []
    seen_urls: set[str] = set()

    for label, url in _MARKDOWN_LINK_RE.findall(text):
        if is_hallucinated_download_url(url):
            continue
        normalized = normalize_outbound_asset(
            {"name": label.strip(), "url": url, "source": "markdown_link"},
            default_source="markdown_link",
        )
        if normalized is not None and normalized["url"] not in seen_urls:
            assets.append(normalized)
            seen_urls.add(normalized["url"])

    for label, url in _MARKDOWN_UPLOAD_LINK_RE.findall(text):
        if is_hallucinated_download_url(url):
            continue
        normalized = normalize_outbound_asset(
            {
                "name": label.strip(),
                "url": url,
                "source": "upload_link",
                "type": "file",
            },
            default_source="upload_link",
        )
        if normalized is not None and normalized["url"] not in seen_urls:
            assets.append(normalized)
            seen_urls.add(normalized["url"])

    for url in _URL_RE.findall(text):
        if url in seen_urls or is_hallucinated_download_url(url):
            continue
        normalized = normalize_outbound_asset(
            {"url": url, "source": "raw_url"},
            default_source="raw_url",
        )
        if normalized is not None:
            assets.append(normalized)
            seen_urls.add(normalized["url"])

    return assets


def collect_outbound_assets(
    content: str,
    extra_data: dict | None,
) -> list[dict]:
    """Collect normalized assets from explicit payload, attachments, and content links."""
    assets: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()

    def add_many(items: list[object], *, default_source: str) -> None:
        for item in items:
            normalized = normalize_outbound_asset(item, default_source=default_source)
            if normalized is None:
                continue
            key = (normalized["type"], normalized["url"])
            if key in seen_keys:
                continue
            assets.append(normalized)
            seen_keys.add(key)

    payload = extra_data or {}
    add_many(list(payload.get("outbound_assets") or []), default_source="explicit")
    add_many(list(payload.get("attachments") or []), default_source="attachment")
    add_many(list(extract_content_assets(content)), default_source="content")
    return assets


def enrich_message_extra_data(
    content: str,
    extra_data: dict | None,
) -> dict | None:
    """Return a copy of extra_data with normalized outbound_assets when present."""
    base = dict(extra_data or {})
    assets = collect_outbound_assets(content, base)
    if assets:
        base["outbound_assets"] = assets
    elif "outbound_assets" in base:
        base.pop("outbound_assets", None)
    return base or None