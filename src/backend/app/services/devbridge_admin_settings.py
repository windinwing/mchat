"""Admin-editable DevBridge settings (UI overrides env defaults)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings


class GamecenterBridgeSettings(BaseModel):
    enabled: bool | None = None
    source_root: str = ""
    extra_source_roots: list[str] = Field(default_factory=list)
    write_enabled: bool | None = None
    publish_enabled: bool | None = None
    data_root: str = ""
    build_command: str = ""
    auto_build_after_patch: bool | None = None
    build_timeout_seconds: int | None = None
    cocos_creator_bin: str = ""
    playables_root: str = ""
    sync_extracted_root: str = ""
    playable_base_url: str = ""
    playable_base_urls: list[str] = Field(default_factory=list)
    project_allowlist: str = ""
    bridge_group_scope_only: bool | None = None
    release_keep_builds: int | None = None
    release_keep: int | None = None
    git_auto_commit: bool | None = None


class CustomBridgeProviderSettings(BaseModel):
    """Config-only rooted provider (no extra code registration)."""

    key: str = ""
    title: str = ""
    enabled: bool | None = True
    source_root: str = ""
    extra_source_roots: list[str] = Field(default_factory=list)
    write_enabled: bool | None = True
    publish_enabled: bool | None = False
    data_root: str = ""
    build_command: str = ""
    build_timeout_seconds: int | None = 1800
    cocos_creator_bin: str = ""
    playables_root: str = ""
    sync_extracted_root: str = ""
    playable_base_urls: list[str] = Field(default_factory=list)
    project_allowlist: str = ""
    bridge_group_scope_only: bool | None = True
    release_keep_builds: int | None = 10
    release_keep: int | None = 20


class DevBridgeAdminSettings(BaseModel):
    gamecenter: GamecenterBridgeSettings = Field(default_factory=GamecenterBridgeSettings)
    custom_providers: list[CustomBridgeProviderSettings] = Field(default_factory=list)


def _settings_path() -> Path:
    configured = (getattr(settings, "devbridge_admin_settings_path", None) or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(settings.gamecenter_bridge_data_root).expanduser().resolve().parent / "admin-settings.json"


def load_devbridge_admin_settings() -> DevBridgeAdminSettings:
    path = _settings_path()
    if not path.is_file():
        return DevBridgeAdminSettings()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return DevBridgeAdminSettings()
    if not isinstance(payload, dict):
        return DevBridgeAdminSettings()
    return DevBridgeAdminSettings.model_validate(payload)


def save_devbridge_admin_settings(data: DevBridgeAdminSettings) -> DevBridgeAdminSettings:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return data


def _pick_str(override: str, fallback: str) -> str:
    text = (override or "").strip()
    return text if text else (fallback or "").strip()


def _pick_bool(override: bool | None, fallback: bool) -> bool:
    return fallback if override is None else bool(override)


def _pick_int(override: int | None, fallback: int) -> int:
    return fallback if override is None else int(override)


def resolved_gamecenter_settings() -> dict[str, Any]:
    """Merge admin UI settings over environment defaults."""
    admin = load_devbridge_admin_settings().gamecenter
    extra_roots = admin.extra_source_roots or []
    if not extra_roots:
        env_extra = (getattr(settings, "gamecenter_extra_source_roots", "") or "").strip()
        if env_extra:
            extra_roots = [item.strip() for item in env_extra.split(",") if item.strip()]

    playable_urls = [item.strip() for item in admin.playable_base_urls if item.strip()]
    if not playable_urls:
        env_urls = (getattr(settings, "gamecenter_playable_base_urls", "") or "").strip()
        if env_urls:
            playable_urls = [item.strip() for item in env_urls.split(",") if item.strip()]
        elif settings.gamecenter_playable_base_url:
            playable_urls = [settings.gamecenter_playable_base_url.strip()]

    return {
        "enabled": _pick_bool(admin.enabled, bool(settings.gamecenter_bridge_enabled)),
        "source_root": _pick_str(admin.source_root, settings.gamecenter_source_root),
        "extra_source_roots": extra_roots,
        "write_enabled": _pick_bool(admin.write_enabled, bool(settings.gamecenter_bridge_write_enabled)),
        "publish_enabled": _pick_bool(admin.publish_enabled, bool(settings.gamecenter_publish_enabled)),
        "data_root": _pick_str(admin.data_root, settings.gamecenter_bridge_data_root),
        "build_command": _pick_str(admin.build_command, settings.gamecenter_build_command),
        "auto_build_after_patch": _pick_bool(
            admin.auto_build_after_patch,
            bool(getattr(settings, "gamecenter_auto_build_after_patch", False)),
        ),
        "build_timeout_seconds": _pick_int(
            admin.build_timeout_seconds,
            int(settings.gamecenter_build_timeout_seconds or 1800),
        ),
        "cocos_creator_bin": _pick_str(admin.cocos_creator_bin, settings.gamecenter_cocos_creator_bin),
        "playables_root": _pick_str(admin.playables_root, settings.gamecenter_playables_root),
        "sync_extracted_root": _pick_str(admin.sync_extracted_root, settings.gamecenter_sync_extracted_root),
        "playable_base_url": playable_urls[0] if playable_urls else "",
        "playable_base_urls": playable_urls,
        "project_allowlist": _pick_str(admin.project_allowlist, settings.gamecenter_project_allowlist),
        "bridge_group_scope_only": _pick_bool(
            admin.bridge_group_scope_only,
            bool(settings.gamecenter_bridge_group_scope_only),
        ),
        "release_keep_builds": _pick_int(
            admin.release_keep_builds,
            int(settings.gamecenter_release_keep_builds or 10),
        ),
        "release_keep": _pick_int(admin.release_keep, int(settings.gamecenter_release_keep or 20)),
        "git_auto_commit": _pick_bool(admin.git_auto_commit, bool(getattr(settings, "gamecenter_git_auto_commit", False))),
    }


def resolved_custom_provider_settings(item: CustomBridgeProviderSettings) -> dict[str, Any]:
    playable_urls = [url.strip() for url in item.playable_base_urls if url.strip()]
    return {
        "enabled": _pick_bool(item.enabled, True),
        "source_root": (item.source_root or "").strip(),
        "extra_source_roots": [root.strip() for root in item.extra_source_roots if root.strip()],
        "write_enabled": _pick_bool(item.write_enabled, True),
        "publish_enabled": _pick_bool(item.publish_enabled, False),
        "data_root": (item.data_root or "").strip(),
        "build_command": (item.build_command or "").strip(),
        "auto_build_after_patch": _pick_bool(item.auto_build_after_patch, False),
        "build_timeout_seconds": _pick_int(item.build_timeout_seconds, 1800),
        "cocos_creator_bin": (item.cocos_creator_bin or "").strip(),
        "playables_root": (item.playables_root or "").strip(),
        "sync_extracted_root": (item.sync_extracted_root or "").strip(),
        "playable_base_url": playable_urls[0] if playable_urls else "",
        "playable_base_urls": playable_urls,
        "project_allowlist": (item.project_allowlist or "").strip(),
        "bridge_group_scope_only": _pick_bool(item.bridge_group_scope_only, True),
        "release_keep_builds": _pick_int(item.release_keep_builds, 10),
        "release_keep": _pick_int(item.release_keep, 20),
    }


def list_resolved_custom_providers() -> list[tuple[str, str, dict[str, Any]]]:
    """Return (key, title, resolved_settings) for each valid custom provider."""
    import re

    seen: set[str] = set()
    items: list[tuple[str, str, dict[str, Any]]] = []
    for raw in load_devbridge_admin_settings().custom_providers:
        key = (raw.key or "").strip().lower()
        if not key or key == "gamecenter" or key in seen:
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", key):
            continue
        cfg = resolved_custom_provider_settings(raw)
        if not cfg["source_root"]:
            continue
        title = (raw.title or key).strip() or key
        seen.add(key)
        items.append((key, title, cfg))
    return items
