"""Admin API for DevBridge provider settings (UI-managed)."""

from fastapi import APIRouter, Depends

from app.middleware.auth import Permission, require_permission
from app.models.user import User
from app.services.devbridge_admin_settings import (
    DevBridgeAdminSettings,
    load_devbridge_admin_settings,
    resolved_gamecenter_settings,
    save_devbridge_admin_settings,
)

router = APIRouter()


@router.get("/settings", response_model=DevBridgeAdminSettings)
async def get_devbridge_settings(
    _user: User = Depends(require_permission(Permission.DEVBRIDGE_SETTINGS_READ)),
) -> DevBridgeAdminSettings:
    return load_devbridge_admin_settings()


@router.get("/settings/resolved")
async def get_devbridge_resolved_settings(
    _user: User = Depends(require_permission(Permission.DEVBRIDGE_SETTINGS_READ)),
) -> dict:
    return {"gamecenter": resolved_gamecenter_settings()}


@router.put("/settings", response_model=DevBridgeAdminSettings)
async def update_devbridge_settings(
    payload: DevBridgeAdminSettings,
    _user: User = Depends(require_permission(Permission.DEVBRIDGE_SETTINGS_WRITE)),
) -> DevBridgeAdminSettings:
    return save_devbridge_admin_settings(payload)
