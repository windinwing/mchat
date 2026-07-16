"""Convert chat attachments into OpenAI-compatible multimodal content.

Images are embedded as base64 ``image_url`` parts so vision-capable models
(OpenAI GPT-4o, GLM-4V, Ollama llava, LM Studio vision models, …) actually
"see" the pixels. Non-image files keep the textual ``[User sent a file: …]``
annotation.

The OpenAI chat message ``content`` becomes a list of typed parts:

    {"role": "user", "content": [
        {"type": "text", "text": "what's in this image?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,…"}},
    ]}

For models/providers without vision support the caller may fall back to the
plain-text ``attachment_prompt_text`` — but most OpenAI-compatible endpoints
simply ignore image parts they can't process.
"""

from __future__ import annotations

import base64
import binascii
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
from loguru import logger

from app.core.config import settings
from app.services.storage_service import storage_service
from app.services.tenant_files_service import TenantFilesService

#: Max image size to inline as base64 (larger images blow up context & latency).
_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB


def _read_attachment_bytes(url: str, user_id: str) -> tuple[bytes, str] | None:
    """Load raw bytes for an attachment URL.

    Handles two URL shapes produced by the upload flows:
    - ``/api/workspace/files/download?uid=…&subdir=…&path=…`` (tenant chat files)
    - ``/uploads/<key>?…`` (storage_service / MinIO-S3)

    Returns ``(data, mime)`` or ``None`` if the file can't be located.
    """
    if not url:
        return None

    # 1) Tenant workspace file: /api/workspace/files/download?uid=..&subdir=..&path=..
    if "/workspace/files/download" in url:
        parsed = urlparse(url if "://" in url else f"http://x{url}")
        qs = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
        uid = qs.get("uid") or user_id
        subdir = qs.get("subdir")
        path = qs.get("path")
        if subdir and path:
            try:
                target, mime = TenantFilesService().read_file(
                    uid, subdir=subdir, path=path
                )
                return target.read_bytes(), mime
            except HTTPException:
                logger.warning("Failed to read tenant attachment: {}", url)
                return None

    # 2) storage_service /uploads/<key>
    if "/uploads/" in url:
        parsed = urlparse(url if "://" in url else f"http://x{url}")
        key = parsed.path.lstrip("/")
        # strip leading "uploads/" if the proxy path included it
        if key.startswith("uploads/"):
            key = key[len("uploads/"):]
        result = storage_service.fetch_bytes(key)
        if result is not None:
            return result

    return None


def _data_url(data: bytes, mime: str) -> str:
    """Encode bytes as a data: URL for the image_url part."""
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def build_multimodal_content(
    text: str,
    extra_data: dict | None,
    user_id: str,
) -> str | list[dict[str, Any]]:
    """Build OpenAI-compatible message ``content`` for a user turn.

    Returns a plain string when there are no inlineable images (unchanged
    behavior), or a list of typed parts when images are present.
    """
    attachments = (extra_data or {}).get("attachments") or []
    image_atts = [
        a
        for a in attachments
        if str(a.get("mime") or "").startswith("image/") and a.get("url")
    ]

    # No images → keep the legacy text annotation (handles files/videos too).
    if not image_atts:
        from app.utils.chat_upload import attachment_prompt_text

        return attachment_prompt_text(text, extra_data)

    parts: list[dict[str, Any]] = []
    clean_text = (text or "").strip()
    if clean_text:
        parts.append({"type": "text", "text": clean_text})

    for att in attachments:
        url = att.get("url") or ""
        name = att.get("name") or "file"
        mime = str(att.get("mime") or "")

        if mime.startswith("image/"):
            loaded = _read_attachment_bytes(url, user_id)
            if loaded is None:
                # Couldn't load → keep a text note so the model knows.
                parts.append(
                    {"type": "text", "text": f"[User sent an image: {name}, but it could not be loaded]"}
                )
                continue
            data, real_mime = loaded
            if len(data) > _MAX_IMAGE_BYTES:
                parts.append(
                    {
                        "type": "text",
                        "text": f"[User sent an image: {name}, but it is too large ({len(data)} bytes) to inline]",
                    }
                )
                continue
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _data_url(data, real_mime)},
                }
            )
        elif mime.startswith("video/"):
            parts.append(
                {"type": "text", "text": f"[User sent a video: {name}]"}
            )
        else:
            parts.append(
                {"type": "text", "text": f"[User sent a file: {name}]"}
            )

    return parts
