"""Registry for development bridge providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.devbridge import DevBridgeProviderResponse
from app.services.configured_bridge_provider import create_configured_bridge_service
from app.services.devbridge_admin_settings import (
    list_resolved_custom_providers,
    resolved_gamecenter_settings,
)
from app.services.gamecenter_provider import create_gamecenter_bridge_service


@dataclass(slots=True)
class DevBridgeProvider:
    key: str
    title: str
    enabled: bool
    capabilities: list[str]
    service_factory: Any


def _capabilities_for_cfg(cfg: dict) -> list[str]:
    return [
        "project:list",
        "project:status",
        "file:list",
        "file:read",
        "file:patch" if cfg.get("write_enabled") else "",
        "build" if cfg.get("write_enabled") else "",
        "build:list" if cfg.get("write_enabled") else "",
        "change:list" if cfg.get("write_enabled") else "",
        "change:revert" if cfg.get("write_enabled") else "",
        "release:list" if cfg.get("publish_enabled") else "",
        "release:publish" if cfg.get("publish_enabled") else "",
        "release:rollback" if cfg.get("publish_enabled") else "",
    ]


def _factory_for(key: str, cfg: dict):
    if key == "gamecenter":
        return create_gamecenter_bridge_service
    return lambda **kwargs: create_configured_bridge_service(
        key,
        cfg,
        project_allowlist_override=kwargs.get("project_allowlist_override"),
    )


def _providers() -> dict[str, DevBridgeProvider]:
    providers: dict[str, DevBridgeProvider] = {}
    gc = resolved_gamecenter_settings()
    providers["gamecenter"] = DevBridgeProvider(
        key="gamecenter",
        title="GameCenter",
        enabled=bool(gc.get("enabled")),
        capabilities=_capabilities_for_cfg(gc),
        service_factory=_factory_for("gamecenter", gc),
    )
    for key, title, cfg in list_resolved_custom_providers():
        providers[key] = DevBridgeProvider(
            key=key,
            title=title,
            enabled=bool(cfg.get("enabled")),
            capabilities=_capabilities_for_cfg(cfg),
            service_factory=_factory_for(key, cfg),
        )
    return providers


def list_devbridge_providers() -> list[DevBridgeProviderResponse]:
    return [
        DevBridgeProviderResponse(
            key=provider.key,
            title=provider.title,
            enabled=provider.enabled,
            capabilities=[item for item in provider.capabilities if item],
        )
        for provider in _providers().values()
    ]


def get_devbridge_provider(key: str) -> DevBridgeProvider:
    provider = _providers().get((key or "").strip().lower())
    if provider is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Dev bridge provider not found")
    return provider
