"""Health check API router."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.knowledge.milvus_client import milvus_client
from app.knowledge.milvus_runtime import get_milvus_runtime

router = APIRouter()


def _milvus_health_status() -> str:
    """Reflect admin-persisted Milvus config and live connection, not .env defaults."""
    runtime = get_milvus_runtime()
    if not runtime.enabled:
        return "disabled"
    if milvus_client._connected:
        return "connected"
    return "disconnected"


@router.get("")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Basic health check endpoint."""
    db_ok = False

    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    overall = "healthy" if db_ok else "degraded"
    if getattr(settings, "maintenance_mode", False):
        overall = "maintenance"

    return {
        "status": overall,
        "database": "connected" if db_ok else "disconnected",
        "milvus": _milvus_health_status(),
        "maintenance_mode": bool(getattr(settings, "maintenance_mode", False)),
        "server_ops_skills_enabled": bool(
            getattr(settings, "server_ops_skills_enabled", False)
        ),
    }


@router.get("/metrics")
async def metrics():
    """Basic metrics endpoint."""
    import sys
    import time

    from app.core.skills_pool import pool_stats

    return {
        "uptime": time.time(),
        "python_version": sys.version,
        "platform": sys.platform,
        "skills_pool": pool_stats(),
    }
