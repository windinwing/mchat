"""Save chat attachment files and build LLM-facing message text."""

from __future__ import annotations

import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.services.storage_service import storage_service

_ALLOWED_MIME_PREFIXES = ("image/", "text/", "video/")
_ALLOWED_MIME_EXACT = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".md",
}


def _safe_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\-]+", "_", base, flags=re.UNICODE)
    return base[:180] or "upload"


def _guess_ext(filename: str, content_type: str | None) -> str:
    ext = Path(filename).suffix.lower()
    if ext in _ALLOWED_EXTENSIONS:
        return ext
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed and guessed in _ALLOWED_EXTENSIONS:
            return guessed
    return ext or ""


def validate_chat_attachment(
    filename: str,
    content_type: str | None,
    size: int,
) -> None:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )
    if size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large (max {settings.max_upload_size_mb}MB)",
        )

    ext = Path(filename or "").suffix.lower()
    mime = (content_type or "").split(";")[0].strip().lower()

    if ext and ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed: {ext}",
        )
    if mime and not (
        mime.startswith(_ALLOWED_MIME_PREFIXES)
        or mime in _ALLOWED_MIME_EXACT
    ):
        if ext not in _ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not allowed: {mime}",
            )


async def save_chat_attachment(
    file: UploadFile,
    *,
    user_id: str | None = None,
    conversation_id: str | None = None,
) -> dict:
    """Persist upload; tenant chats go to uploads/chat/{conversation_id}/."""
    raw_name = file.filename or "upload"
    data = await file.read()
    validate_chat_attachment(raw_name, file.content_type, len(data))

    if user_id and conversation_id:
        from app.services.tenant_files_service import TenantFilesService

        return TenantFilesService.save_chat_bytes(
            user_id,
            conversation_id,
            filename=raw_name,
            data=data,
            content_type=file.content_type,
        )

    ext = _guess_ext(raw_name, file.content_type)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored = storage_service.save_bytes(
        data,
        filename=stored_name,
        content_type=file.content_type,
        prefix="chat",
    )

    mime = file.content_type or mimetypes.guess_type(raw_name)[0] or "application/octet-stream"
    return {
        "url": stored.url,
        "name": _safe_filename(raw_name),
        "mime": mime,
        "size": len(data),
    }


def attachment_prompt_text(content: str, extra_data: dict | None) -> str:
    """Append attachment descriptions for the LLM."""
    attachments = (extra_data or {}).get("attachments") or []
    if not attachments:
        return content

    lines: list[str] = []
    if content and content.strip():
        lines.append(content.strip())

    for att in attachments:
        name = att.get("name") or "file"
        url = att.get("url") or ""
        mime = str(att.get("mime") or "")
        if mime.startswith("image/"):
            lines.append(f"[User sent an image: {name}] URL: {url}")
        elif mime.startswith("video/"):
            lines.append(f"[User sent a video: {name}] URL: {url}")
        else:
            lines.append(f"[User sent a file: {name}] URL: {url}")

    return "\n".join(lines) if lines else content
