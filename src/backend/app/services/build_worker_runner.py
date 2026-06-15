"""Execute a queued DevBridge build job (subprocess in worker process)."""

from __future__ import annotations

from fastapi import HTTPException
from loguru import logger

from app.services.gamecenter_provider import create_gamecenter_bridge_service
from app.services.devbridge_registry import get_devbridge_provider
from app.services.devbridge_admin_settings import load_devbridge_admin_settings


def execute_queued_build_job(job: dict) -> dict:
    slug = str(job.get("slug") or "").strip()
    build_id = str(job.get("build_id") or "").strip()
    if not slug or not build_id:
        logger.error("Build job missing slug or build_id: {}", job)
        return {"ok": False, "error": "invalid job"}

    provider_key = str(job.get("provider_key") or "gamecenter").strip().lower()

    # Resolve the provider's service instance
    if provider_key == "gamecenter":
        service = create_gamecenter_bridge_service()
    else:
        provider = get_devbridge_provider(provider_key)
        if provider is None:
            logger.error("Unknown build provider: {}", provider_key)
            return {"ok": False, "error": f"unknown provider: {provider_key}"}
        # Build service from admin settings for this provider
        from app.services.configured_bridge_provider import create_configured_bridge_service
        admin_settings = load_devbridge_admin_settings()
        cfg = admin_settings.get("custom_providers", {}).get(provider_key, {})
        if not cfg:
            cfg = provider.config if hasattr(provider, 'config') else {}
        service = create_configured_bridge_service(provider_key, cfg)

    try:
        return service.run_queued_build(job)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        logger.warning("Build job failed slug={} build_id={}: {}", slug, build_id, detail)
        return {"ok": False, "error": detail}
    except Exception as exc:
        logger.exception("Build job crashed slug={} build_id={}", slug, build_id)
        return {"ok": False, "error": str(exc)}
