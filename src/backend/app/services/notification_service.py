"""Unified SMS notification with whitelist, rate limit, and audit log."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.sms_send_log import SmsSendLog
from app.services.notification_providers import get_sms_provider
from app.services.sms.base import is_valid_cn_mobile, normalize_phone

_memory_cooldown: dict[str, float] = {}
_memory_lock = Lock()

WORKFLOW_ALERT_TEMPLATE = "workflow_alert"


class NotificationService:
    """Send notifications with whitelist + rate limit. Default provider: dev (log only)."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db

    @staticmethod
    def phone_allowlist() -> list[str]:
        raw = getattr(settings, "sms_phone_allowlist", None) or []
        if isinstance(raw, str):
            return [normalize_phone(p) for p in raw.split(",") if p.strip()]
        return [normalize_phone(str(p)) for p in raw if str(p).strip()]

    @staticmethod
    def alert_phones() -> list[str]:
        raw = getattr(settings, "sms_alert_phones", None) or []
        if isinstance(raw, str):
            return [normalize_phone(p) for p in raw.split(",") if p.strip()]
        return [normalize_phone(str(p)) for p in raw if str(p).strip()]

    def is_phone_allowed(self, phone: str, *, source: str) -> bool:
        normalized = normalize_phone(phone)
        if not is_valid_cn_mobile(normalized):
            return False
        allowlist = self.phone_allowlist()
        if source == "workflow_alert":
            alert = self.alert_phones()
            if alert:
                return normalized in alert
        if allowlist:
            return normalized in allowlist
        return False

    def check_rate_limit(self, phone: str) -> bool:
        normalized = normalize_phone(phone)
        cooldown = max(30, int(getattr(settings, "sms_send_cooldown_seconds", 60) or 60))
        now = time.time()

        try:
            import redis

            client = redis.from_url(settings.redis_url, decode_responses=True)
            key = f"sms:cooldown:{normalized}"
            if client.set(key, "1", nx=True, ex=cooldown):
                return True
            return False
        except Exception:
            with _memory_lock:
                last = _memory_cooldown.get(normalized, 0.0)
                if now - last < cooldown:
                    return False
                _memory_cooldown[normalized] = now
                return True

    def _provider(self, name: str | None):
        return get_sms_provider(name or settings.sms_default_provider or "dev")

    def _render_workflow_alert(self, params: dict[str, Any]) -> str:
        wf = str(params.get("workflow_name") or params.get("workflow") or "Workflow")
        event = str(params.get("event") or "alert")
        msg = str(params.get("message") or "")[:120]
        run_id = str(params.get("run_id") or "")[:12]
        parts = [f"MChat[{event}]", wf]
        if run_id:
            parts.append(f"#{run_id}")
        if msg:
            parts.append(msg)
        return " ".join(parts)[:500]

    def send_sms(
        self,
        *,
        phone: str,
        source: str = "skill",
        user_id: str | None = None,
        provider: str | None = None,
        content: str | None = None,
        template: str | None = None,
        template_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_phone(phone)
        if not self.is_phone_allowed(normalized, source=source):
            return {
                "ok": False,
                "message": "手机号不在白名单或格式无效",
                "error": "phone_not_allowed",
            }
        if not self.check_rate_limit(normalized):
            return {
                "ok": False,
                "message": f"发送过于频繁，请 {settings.sms_send_cooldown_seconds}s 后重试",
                "error": "rate_limited",
            }

        prov = self._provider(provider)
        tpl = (template or "").strip()
        params = dict(template_params or {})

        if tpl == WORKFLOW_ALERT_TEMPLATE or source == "workflow_alert":
            body = self._render_workflow_alert(params)
            if tpl and hasattr(prov, "send_template") and prov.name not in ("dev",):
                result = prov.send_template(
                    normalized,
                    template_code=tpl,
                    template_params=params,
                )
            else:
                result = prov.send_text(normalized, body)
        elif tpl and hasattr(prov, "send_template") and prov.name not in ("dev",):
            result = prov.send_template(
                normalized,
                template_code=tpl,
                template_params=params,
            )
        elif content:
            result = prov.send_text(normalized, content[:500])
        else:
            result = prov.send_text(
                normalized,
                str(params.get("message") or "MChat notify ping"),
            )

        self._log_row(
            user_id=user_id,
            phone=normalized,
            provider=result.provider,
            source=source,
            template=tpl or None,
            content_preview=(content or self._render_workflow_alert(params))[:200],
            ok=result.ok,
            provider_code=result.provider_code,
            error=None if result.ok else result.message,
        )
        return {
            "ok": result.ok,
            "message": result.message,
            "provider": result.provider,
            "phone": normalized[:3] + "****" + normalized[-4:],
            "provider_code": result.provider_code,
        }

    def send_workflow_alert_sms(
        self,
        *,
        event: str,
        workflow_name: str,
        run_id: str,
        message: str,
    ) -> list[dict[str, Any]]:
        if not getattr(settings, "sms_workflow_alert_enabled", False):
            return []
        phones = self.alert_phones() or self.phone_allowlist()
        results: list[dict[str, Any]] = []
        params = {
            "event": event,
            "workflow_name": workflow_name,
            "run_id": run_id,
            "message": message,
        }
        for phone in phones:
            out = self.send_sms(
                phone=phone,
                source="workflow_alert",
                template=WORKFLOW_ALERT_TEMPLATE,
                template_params=params,
                provider=settings.sms_default_provider,
            )
            results.append(out)
        return results

    def _log_row(
        self,
        *,
        user_id: str | None,
        phone: str,
        provider: str,
        source: str,
        template: str | None,
        content_preview: str,
        ok: bool,
        provider_code: str,
        error: str | None,
    ) -> None:
        masked = phone[:3] + "****" + phone[-4:]
        if self.db is None:
            logger.info(
                "sms provider={} phone={} ok={} source={}",
                provider,
                masked,
                ok,
                source,
            )
            return
        self.db.add(
            SmsSendLog(
                user_id=user_id,
                phone=phone,
                provider=provider,
                source=source,
                template_code=template,
                content_preview=content_preview,
                status="success" if ok else "failed",
                provider_code=provider_code,
                error_message=error,
                created_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    def sync_send_sms(**kwargs: Any) -> dict[str, Any]:
        return NotificationService(db=None).send_sms(**kwargs)
