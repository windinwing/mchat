"""Execute a queued DevBridge build job (subprocess in worker process)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException
from loguru import logger

from app.services.gamecenter_provider import create_gamecenter_bridge_service


def execute_queued_build_job(job: dict) -> dict:
    slug = str(job.get("slug") or "").strip()
    build_id = str(job.get("build_id") or "").strip()
    if not slug or not build_id:
        logger.error("Build job missing slug or build_id: {}", job)
        return {"ok": False, "error": "invalid job"}

    provider_key = str(job.get("provider_key") or "gamecenter").strip().lower()
    if provider_key != "gamecenter":
        logger.error("Unsupported build provider: {}", provider_key)
        return {"ok": False, "error": f"unsupported provider: {provider_key}"}

    service = create_gamecenter_bridge_service()
    try:
        return service.run_queued_build(job)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        logger.warning("Build job failed slug={} build_id={}: {}", slug, build_id, detail)
        return {"ok": False, "error": detail}
