"""Tenant workspace uploads listing and management."""

from __future__ import annotations

import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.schemas.tenant_files import TenantFileEntry, TenantFileUploadResponse
from app.utils.chat_upload import validate_chat_attachment
from app.workspace.paths import ensure_execution_layout, tenant_uploads_dir

_ALLOWED_SUBDIRS = {"user", "chat", "workflow", "exports"}


def _safe_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\-]+", "_", base, flags=re.UNICODE)
    return base[:180] or "upload"


def _resolve_subdir(raw: str | None) -> str:
    sub = (raw or "user").strip().strip("/").replace("\\", "/")
    if not sub or ".." in sub.split("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid subdir",
        )
    root_segment = sub.split("/")[0]
    if root_segment not in _ALLOWED_SUBDIRS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"subdir must start with one of: {', '.join(sorted(_ALLOWED_SUBDIRS))}",
        )
    return sub


def _resolve_path(user_id: str, subdir: str, relative: str) -> Path:
    rel = (relative or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path",
        )
    base = tenant_uploads_dir(user_id)
    ensure_execution_layout(base.parent)
    target = (base / subdir / rel).resolve()
    allowed_root = (base / subdir).resolve()
    try:
        target.relative_to(allowed_root)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path escapes uploads directory",
        ) from e
    return target


def _file_url(user_id: str, subdir: str, relative: str) -> str:
    from urllib.parse import quote

    rel = relative.replace("\\", "/").lstrip("/")
    return f"/api/workspace/files/download?subdir={quote(subdir)}&path={quote(rel)}"


class TenantFilesService:
    def list_files(self, user_id: str, *, subdir: str = "user") -> list[TenantFileEntry]:
        sub = _resolve_subdir(subdir)
        base = tenant_uploads_dir(user_id) / sub
        ensure_execution_layout(tenant_uploads_dir(user_id).parent)
        base.mkdir(parents=True, exist_ok=True)

        items: list[TenantFileEntry] = []
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(base).as_posix()
            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            items.append(
                TenantFileEntry(
                    path=rel,
                    name=path.name,
                    size=stat.st_size,
                    is_dir=path.is_dir(),
                    modified_at=modified,
                )
            )
        return items

    async def upload_file(
        self,
        user_id: str,
        file: UploadFile,
        *,
        subdir: str = "user",
        relative_dir: str = "",
    ) -> TenantFileUploadResponse:
        sub = _resolve_subdir(subdir)
        raw_name = file.filename or "upload"
        data = await file.read()
        validate_chat_attachment(raw_name, file.content_type, len(data))

        rel_dir = (relative_dir or "").strip().replace("\\", "/").strip("/")
        if rel_dir and ".." in rel_dir.split("/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid relative_dir",
            )

        stored_name = _safe_filename(raw_name)
        if rel_dir:
            rel_path = f"{rel_dir}/{stored_name}"
        else:
            ext = Path(stored_name).suffix
            rel_path = f"{uuid.uuid4().hex}{ext}" if not stored_name else stored_name

        target = _resolve_path(user_id, sub, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        return TenantFileUploadResponse(
            path=rel_path.replace("\\", "/"),
            name=stored_name,
            size=len(data),
            url=_file_url(user_id, sub, rel_path),
        )

    def delete_path(self, user_id: str, *, subdir: str, path: str) -> None:
        sub = _resolve_subdir(subdir)
        target = _resolve_path(user_id, sub, path)
        if not target.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )
        if target.is_dir():
            import shutil

            shutil.rmtree(target)
        else:
            target.unlink()

    def mkdir(self, user_id: str, *, subdir: str, name: str) -> str:
        sub = _resolve_subdir(subdir)
        safe = _safe_filename(name)
        target = _resolve_path(user_id, sub, safe)
        target.mkdir(parents=True, exist_ok=True)
        return f"{sub}/{safe}"

    def read_file(self, user_id: str, *, subdir: str, path: str) -> tuple[Path, str]:
        sub = _resolve_subdir(subdir)
        target = _resolve_path(user_id, sub, path)
        if not target.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if target.stat().st_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File too large to download via API",
            )
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return target, mime

    @staticmethod
    def save_chat_bytes(
        user_id: str,
        conversation_id: str,
        *,
        filename: str,
        data: bytes,
        content_type: str | None,
    ) -> dict:
        """Persist chat attachment under uploads/chat/{conversation_id}/."""
        validate_chat_attachment(filename, content_type, len(data))
        subdir = f"chat/{conversation_id}"
        rel_dir = ""
        safe = _safe_filename(filename)
        ext = Path(safe).suffix
        rel_path = f"{uuid.uuid4().hex}{ext}" if ext else f"{uuid.uuid4().hex}"
        target = _resolve_path(user_id, subdir, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        mime = content_type or mimetypes.guess_type(safe)[0] or "application/octet-stream"
        return {
            "url": _file_url(user_id, subdir, rel_path),
            "name": safe,
            "mime": mime,
            "size": len(data),
            "tenant_path": f"{subdir}/{rel_path}",
        }
