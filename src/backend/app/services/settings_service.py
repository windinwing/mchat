"""Settings service - business logic for system configuration."""

import json
import os
from collections import deque
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.utils.upload_paths import resolve_upload_root
from app.utils.secret_mask import is_secret_mask, mask_secret
from app.knowledge.milvus_client import milvus_client
from app.knowledge.milvus_runtime import apply_milvus_runtime
from app.skill.ops_policy import (
    SCOPE_SERVER_OPS,
    is_server_ops_skill,
    sync_notification_settings_from_db,
    sync_server_ops_settings_from_db,
)
from app.skill.shell_allowlist import normalize_allowlist_entries
from app.models.setting import Setting
from app.schemas.settings import AppSettingsResponse, AppSettingsUpdate


DEFAULT_SETTINGS = AppSettingsResponse()

_SECRET_SETTING_KEYS = frozenset({"s3_secret_key", "embedding_api_key"})


class SettingsService:
    """Handles system settings persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_settings(self) -> AppSettingsResponse:
        """Get all system settings with defaults."""
        result = await self.db.execute(select(Setting))
        rows = {r.key: r.value for r in result.scalars().all()}

        def get_val(key: str, default):
            if key not in rows:
                return default
            raw = rows[key]
            if isinstance(default, bool):
                return raw.lower() in ("true", "1", "yes")
            if isinstance(default, int):
                try:
                    return int(raw)
                except (ValueError, TypeError):
                    return default
            if isinstance(default, list):
                try:
                    return json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    return default
            return raw

        milvus_enabled = get_val("milvus_enabled", DEFAULT_SETTINGS.milvus_enabled)
        milvus_host = get_val("milvus_host", DEFAULT_SETTINGS.milvus_host)
        milvus_port = get_val("milvus_port", DEFAULT_SETTINGS.milvus_port)
        storage_backend = get_val("storage_backend", DEFAULT_SETTINGS.storage_backend)
        upload_default = (
            os.environ.get("UPLOAD_DIR", "").strip()
            or settings.upload_dir
            or DEFAULT_SETTINGS.upload_dir
        )
        upload_dir_raw = get_val("upload_dir", upload_default)
        upload_dir = str(resolve_upload_root(upload_dir_raw))
        max_upload_size_mb = get_val(
            "max_upload_size_mb", DEFAULT_SETTINGS.max_upload_size_mb
        )
        s3_endpoint = get_val("s3_endpoint", DEFAULT_SETTINGS.s3_endpoint)
        s3_region = get_val("s3_region", DEFAULT_SETTINGS.s3_region)
        s3_access_key = get_val("s3_access_key", DEFAULT_SETTINGS.s3_access_key)
        s3_secret_key = get_val("s3_secret_key", DEFAULT_SETTINGS.s3_secret_key)
        s3_bucket = get_val("s3_bucket", DEFAULT_SETTINGS.s3_bucket)
        s3_use_ssl = get_val("s3_use_ssl", DEFAULT_SETTINGS.s3_use_ssl)
        s3_public_base_url = get_val(
            "s3_public_base_url", DEFAULT_SETTINGS.s3_public_base_url
        )
        s3_force_path_style = get_val(
            "s3_force_path_style", DEFAULT_SETTINGS.s3_force_path_style
        )
        worker_enabled = get_val("worker_enabled", settings.worker_enabled)
        worker_timezone = get_val("worker_timezone", settings.worker_timezone)
        worker_log_cleanup_enabled = get_val(
            "worker_log_cleanup_enabled", settings.worker_log_cleanup_enabled
        )
        worker_log_retention_days = get_val(
            "worker_log_retention_days", settings.worker_log_retention_days
        )
        worker_usage_reset_enabled = get_val(
            "worker_usage_reset_enabled", settings.worker_usage_reset_enabled
        )
        embedding_provider = get_val(
            "embedding_provider", DEFAULT_SETTINGS.embedding_provider
        )
        embedding_model = get_val("embedding_model", DEFAULT_SETTINGS.embedding_model)
        embedding_api_base = get_val(
            "embedding_api_base", DEFAULT_SETTINGS.embedding_api_base
        )
        embedding_dimension = get_val(
            "embedding_dimension", DEFAULT_SETTINGS.embedding_dimension
        )
        embedding_api_key = get_val(
            "embedding_api_key", DEFAULT_SETTINGS.embedding_api_key
        )
        maintenance_mode = get_val(
            "maintenance_mode", DEFAULT_SETTINGS.maintenance_mode
        )
        server_ops_skills_enabled = get_val(
            "server_ops_skills_enabled", DEFAULT_SETTINGS.server_ops_skills_enabled
        )
        server_ops_skill_allowlist = get_val(
            "server_ops_skill_allowlist", DEFAULT_SETTINGS.server_ops_skill_allowlist
        )
        if not isinstance(server_ops_skill_allowlist, list):
            server_ops_skill_allowlist = []
        shell_raw = get_val(
            "server_ops_shell_allowlist", DEFAULT_SETTINGS.server_ops_shell_allowlist
        )
        try:
            server_ops_shell_allowlist = normalize_allowlist_entries(shell_raw)
        except ValueError:
            server_ops_shell_allowlist = []

        apply_milvus_runtime(
            enabled=milvus_enabled,
            host=milvus_host,
            port=milvus_port,
        )
        settings.milvus_enabled = milvus_enabled
        settings.milvus_host = milvus_host
        settings.milvus_port = milvus_port
        settings.embedding_provider = embedding_provider
        settings.embedding_model = embedding_model
        settings.embedding_api_base = embedding_api_base
        settings.embedding_dimension = embedding_dimension
        settings.embedding_api_key = embedding_api_key
        settings.maintenance_mode = maintenance_mode
        allowlist_runtime = server_ops_skill_allowlist or None
        sync_server_ops_settings_from_db(
            enabled=server_ops_skills_enabled,
            allowlist=allowlist_runtime,
            shell_allowlist=server_ops_shell_allowlist,
        )

        notification_skills_enabled = get_val(
            "notification_skills_enabled", DEFAULT_SETTINGS.notification_skills_enabled
        )
        notification_skill_allowlist = get_val(
            "notification_skill_allowlist", DEFAULT_SETTINGS.notification_skill_allowlist
        )
        if not isinstance(notification_skill_allowlist, list):
            notification_skill_allowlist = ["mchat-notify"]
        sms_default_provider = get_val(
            "sms_default_provider", DEFAULT_SETTINGS.sms_default_provider
        )
        sms_phone_allowlist = get_val(
            "sms_phone_allowlist", DEFAULT_SETTINGS.sms_phone_allowlist
        )
        if not isinstance(sms_phone_allowlist, list):
            sms_phone_allowlist = []
        sms_alert_phones = get_val("sms_alert_phones", DEFAULT_SETTINGS.sms_alert_phones)
        if not isinstance(sms_alert_phones, list):
            sms_alert_phones = []
        sms_send_cooldown_seconds = get_val(
            "sms_send_cooldown_seconds", DEFAULT_SETTINGS.sms_send_cooldown_seconds
        )
        sms_workflow_alert_enabled = get_val(
            "sms_workflow_alert_enabled", DEFAULT_SETTINGS.sms_workflow_alert_enabled
        )
        sync_notification_settings_from_db(
            enabled=notification_skills_enabled,
            allowlist=notification_skill_allowlist or None,
            sms_default_provider=str(sms_default_provider),
            sms_phone_allowlist=sms_phone_allowlist,
            sms_alert_phones=sms_alert_phones,
            sms_workflow_alert_enabled=sms_workflow_alert_enabled,
            sms_send_cooldown_seconds=int(sms_send_cooldown_seconds),
        )

        # Keep runtime storage settings in sync with persisted settings.
        settings.storage_backend = storage_backend
        env_upload = os.environ.get("UPLOAD_DIR", "").strip()
        settings.upload_dir = (
            str(resolve_upload_root(env_upload)) if env_upload else upload_dir
        )
        settings.max_upload_size_mb = max_upload_size_mb
        settings.s3_endpoint = s3_endpoint
        settings.s3_region = s3_region
        settings.s3_access_key = s3_access_key
        settings.s3_secret_key = s3_secret_key
        settings.s3_bucket = s3_bucket
        settings.s3_use_ssl = s3_use_ssl
        settings.s3_public_base_url = s3_public_base_url
        settings.s3_force_path_style = s3_force_path_style
        settings.worker_enabled = worker_enabled
        settings.worker_timezone = worker_timezone
        settings.worker_log_cleanup_enabled = worker_log_cleanup_enabled
        settings.worker_log_retention_days = worker_log_retention_days
        settings.worker_usage_reset_enabled = worker_usage_reset_enabled

        return AppSettingsResponse(
            site_name=get_val("site_name", DEFAULT_SETTINGS.site_name),
            site_description=get_val("site_description", DEFAULT_SETTINGS.site_description),
            language=get_val("language", DEFAULT_SETTINGS.language),
            timezone=get_val("timezone", DEFAULT_SETTINGS.timezone),
            max_file_size=get_val("max_file_size", DEFAULT_SETTINGS.max_file_size),
            allowed_file_types=get_val("allowed_file_types", DEFAULT_SETTINGS.allowed_file_types),
            enable_websocket=get_val("enable_websocket", DEFAULT_SETTINGS.enable_websocket),
            enable_streaming=get_val("enable_streaming", DEFAULT_SETTINGS.enable_streaming),
            rate_limit_per_min=get_val("rate_limit_per_min", DEFAULT_SETTINGS.rate_limit_per_min),
            maintenance_mode=maintenance_mode,
            server_ops_skills_enabled=server_ops_skills_enabled,
            server_ops_skill_allowlist=server_ops_skill_allowlist,
            server_ops_shell_allowlist=server_ops_shell_allowlist,
            milvus_enabled=milvus_enabled,
            milvus_host=milvus_host,
            milvus_port=milvus_port,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_api_base=embedding_api_base,
            embedding_dimension=embedding_dimension,
            embedding_api_key=mask_secret(embedding_api_key),
            storage_backend=storage_backend,
            upload_dir=upload_dir,
            max_upload_size_mb=max_upload_size_mb,
            s3_endpoint=s3_endpoint,
            s3_region=s3_region,
            s3_access_key=s3_access_key,
            s3_secret_key=mask_secret(s3_secret_key),
            s3_bucket=s3_bucket,
            s3_use_ssl=s3_use_ssl,
            s3_public_base_url=s3_public_base_url,
            s3_force_path_style=s3_force_path_style,
            worker_enabled=worker_enabled,
            worker_timezone=worker_timezone,
            worker_log_cleanup_enabled=worker_log_cleanup_enabled,
            worker_log_retention_days=worker_log_retention_days,
            worker_usage_reset_enabled=worker_usage_reset_enabled,
            notification_skills_enabled=notification_skills_enabled,
            notification_skill_allowlist=notification_skill_allowlist,
            sms_default_provider=str(sms_default_provider),
            sms_phone_allowlist=sms_phone_allowlist,
            sms_alert_phones=sms_alert_phones,
            sms_send_cooldown_seconds=int(sms_send_cooldown_seconds),
            sms_workflow_alert_enabled=sms_workflow_alert_enabled,
        )

    async def update_settings(self, data: AppSettingsUpdate) -> AppSettingsResponse:
        """Update settings, creating keys that don't exist."""
        updates = data.model_dump(exclude_unset=True)

        for secret_key in _SECRET_SETTING_KEYS:
            if secret_key in updates and is_secret_mask(updates.get(secret_key)):
                updates.pop(secret_key)

        # Fetch existing settings
        result = await self.db.execute(select(Setting))
        existing: dict[str, Setting] = {r.key: r for r in result.scalars().all()}

        if "upload_dir" in updates and updates["upload_dir"]:
            updates["upload_dir"] = str(
                resolve_upload_root(str(updates["upload_dir"]))
            )

        if "server_ops_shell_allowlist" in updates:
            raw_shell = updates.pop("server_ops_shell_allowlist")
            try:
                normalized = normalize_allowlist_entries(raw_shell)
            except ValueError as e:
                from fastapi import HTTPException, status

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                ) from e
            updates["server_ops_shell_allowlist"] = normalized

        for db_key, new_val in updates.items():
            val_str: str
            if isinstance(new_val, list):
                val_str = json.dumps(new_val, ensure_ascii=False)
            elif isinstance(new_val, bool):
                val_str = "true" if new_val else "false"
            else:
                val_str = str(new_val)

            if db_key in existing:
                existing[db_key].value = val_str
            else:
                self.db.add(Setting(key=db_key, value=val_str, category="general"))

        await self.db.flush()

        result = await self.get_settings()
        if any(k.startswith("milvus_") for k in updates):
            await milvus_client.reconnect()
        elif any(k.startswith("embedding_") for k in updates):
            await milvus_client.reconnect()
            if milvus_client._connected:
                await milvus_client.create_collection()
        return result

    async def test_milvus_connection(
        self, *, enabled: bool, host: str, port: int
    ) -> dict:
        """Test Milvus connectivity with given settings (does not persist)."""
        from app.knowledge import milvus_runtime

        saved = milvus_runtime.get_milvus_runtime()
        apply_milvus_runtime(enabled=enabled, host=host, port=port)
        try:
            ok = await milvus_client.reconnect()
            if ok:
                return {"ok": True, "message": f"已连接 Milvus {host}:{port}"}
            if not enabled:
                return {"ok": True, "message": "Milvus 已禁用（仅使用数据库全文检索）"}
            return {"ok": False, "message": f"无法连接 Milvus {host}:{port}"}
        finally:
            apply_milvus_runtime(
                enabled=saved.enabled,
                host=saved.host,
                port=saved.port,
            )
            await milvus_client.reconnect()

    async def get_log_tail(
        self,
        *,
        source: str = "app",
        lines: int = 200,
    ) -> dict:
        """Read the last N lines from backend log files."""
        safe_lines = max(20, min(lines, 1000))
        log_file = "error.log" if source == "error" else "app.log"
        path = Path("logs") / log_file

        if not path.exists():
            return {
                "source": source,
                "lines": [f"日志文件不存在: {path}"],
            }

        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                tail = list(deque(f, maxlen=safe_lines))
        except Exception as e:
            return {
                "source": source,
                "lines": [f"读取日志失败: {e}"],
            }

        return {
            "source": source,
            "lines": [line.rstrip("\n") for line in tail],
        }
