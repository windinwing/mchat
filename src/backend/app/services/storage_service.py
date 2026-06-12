"""File storage abstraction for local filesystem and S3-compatible services."""

from __future__ import annotations

import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.core.config import settings
from app.utils.upload_paths import resolve_upload_root, safe_upload_file_path
from app.utils.upload_tokens import signed_upload_url


@dataclass
class StoredObject:
    key: str
    url: str
    local_path: Path | None = None


def _sanitize_filename(filename: str) -> str:
    safe = Path(filename or "upload").name
    safe = re.sub(r"[^\w.\-]+", "_", safe, flags=re.UNICODE)
    return safe or "upload"


def _normalize_prefix(prefix: str | None) -> str:
    if not prefix:
        return ""
    return prefix.strip().strip("/")


def _build_storage_key(filename: str, prefix: str | None = None) -> str:
    ext = Path(_sanitize_filename(filename)).suffix
    object_name = f"{uuid.uuid4().hex}{ext}"
    normalized = _normalize_prefix(prefix)
    return f"{normalized}/{object_name}" if normalized else object_name


def _build_s3_endpoint_url() -> str | None:
    endpoint = (settings.s3_endpoint or "").strip()
    if not endpoint:
        return None
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint.rstrip("/")
    scheme = "https" if settings.s3_use_ssl else "http"
    return f"{scheme}://{endpoint.rstrip('/')}"


class StorageService:
    """Storage facade used by upload and knowledge workflows."""

    def save_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str | None = None,
        prefix: str | None = None,
    ) -> StoredObject:
        """Save bytes to the configured backend and return location metadata."""
        key = _build_storage_key(filename, prefix)
        backend = (settings.storage_backend or "local").strip().lower()

        if backend in ("s3", "minio"):
            return self._save_s3(data, key=key, content_type=content_type)
        return self._save_local(data, key=key)

    def _save_local(self, data: bytes, *, key: str) -> StoredObject:
        root = resolve_upload_root()
        full_path = root / key
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)
        return StoredObject(
            key=key,
            url=signed_upload_url(key),
            local_path=full_path,
        )

    def _save_s3(
        self,
        data: bytes,
        *,
        key: str,
        content_type: str | None,
    ) -> StoredObject:
        endpoint_url = _build_s3_endpoint_url()

        try:
            import boto3
            from botocore.config import Config
        except Exception as exc:
            raise RuntimeError(
                "S3/MinIO storage requires boto3. Install backend dependencies first."
            ) from exc

        client = boto3.client(
            "s3",
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
            region_name=settings.s3_region or None,
            endpoint_url=endpoint_url,
            config=Config(
                s3={
                    "addressing_style": "path"
                    if settings.s3_force_path_style
                    else "auto"
                }
            ),
        )

        client.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )

        # Browser-facing URL: same-origin /uploads proxy (see app.api.uploads).
        # Optional s3_public_base_url for a dedicated CDN / public MinIO gateway.
        public_base = (settings.s3_public_base_url or "").strip().rstrip("/")
        if public_base:
            url = f"{public_base}/{key}"
        else:
            url = signed_upload_url(key)

        return StoredObject(key=key, url=url)

    def is_object_storage(self) -> bool:
        backend = (settings.storage_backend or "local").strip().lower()
        return backend in ("s3", "minio")

    def fetch_bytes(self, key: str) -> tuple[bytes, str] | None:
        """Load object by storage key from MinIO/S3, then local disk fallback."""
        normalized = (key or "").strip().lstrip("/")
        if not normalized or ".." in normalized.split("/"):
            return None

        if self.is_object_storage():
            data = self._fetch_s3_bytes(normalized)
            if data is not None:
                mime, _ = mimetypes.guess_type(normalized)
                return data, mime or "application/octet-stream"

        path = safe_upload_file_path(normalized)
        if path is not None and path.is_file():
            mime, _ = mimetypes.guess_type(str(path))
            return path.read_bytes(), mime or "application/octet-stream"

        return self._fetch_tenant_workflow_bytes(normalized)

    def _fetch_tenant_workflow_bytes(self, key: str) -> tuple[bytes, str] | None:
        """Legacy skill/tenant uploads written under data/tenants/*/uploads/.
        Covers workflow_reports, patent-exports, trade-exports etc."""
        allowed_prefixes = ("workflow_reports/", "patent-exports/", "trade-exports/")
        if not any(key.startswith(p) for p in allowed_prefixes):
            return None
        try:
            from app.workspace.paths import resolve_workspace_root
        except Exception:
            return None
        root = resolve_workspace_root()
        if not root.is_dir():
            return None
        for tenant_dir in root.iterdir():
            if not tenant_dir.is_dir():
                continue
            candidate = tenant_dir / "uploads" / key
            if candidate.is_file():
                mime, _ = mimetypes.guess_type(str(candidate))
                return candidate.read_bytes(), mime or "application/octet-stream"
        return None

    def _fetch_s3_bytes(self, key: str) -> bytes | None:
        endpoint_url = _build_s3_endpoint_url()
        if not endpoint_url or not (settings.s3_bucket or "").strip():
            return None
        try:
            import boto3
            from botocore.config import Config
        except Exception:
            return None

        client = boto3.client(
            "s3",
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
            region_name=settings.s3_region or None,
            endpoint_url=endpoint_url,
            config=Config(
                s3={
                    "addressing_style": "path"
                    if settings.s3_force_path_style
                    else "auto"
                }
            ),
        )
        try:
            response = client.get_object(
                Bucket=settings.s3_bucket,
                Key=key,
            )
            body = response.get("Body")
            if body is None:
                return None
            return body.read()
        except Exception as exc:
            logger.warning("S3 fetch failed for key {}: {}", key, exc)
            return None


storage_service = StorageService()
