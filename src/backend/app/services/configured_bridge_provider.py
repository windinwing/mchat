"""Factory for rooted DevBridge providers from merged settings dicts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.rooted_project_bridge_service import (
    RootedProjectBridgeConfig,
    RootedProjectBridgeService,
)


def _global_project_allowlist(cfg: dict[str, Any]) -> set[str] | None:
    items = {
        item.strip()
        for item in (cfg.get("project_allowlist") or "").split(",")
        if item.strip()
    }
    return items or None


def _group_allowlist_for_provider(
    provider_key: str,
    *,
    project_allowlist_override: set[str] | None = None,
) -> set[str] | None:
    if project_allowlist_override is not None:
        return project_allowlist_override
    from app.bot.tool_runtime import get_bot_group_devbridge_allowlists

    group_allowlists = get_bot_group_devbridge_allowlists()
    if group_allowlists is not None:
        return set(group_allowlists.get(provider_key, set()))
    return None


def bridge_config_from_settings(provider_key: str, cfg: dict[str, Any]) -> RootedProjectBridgeConfig:
    key = (provider_key or "").strip().lower()
    extra_roots = tuple(
        Path(item).expanduser().resolve()
        for item in (cfg.get("extra_source_roots") or [])
        if str(item).strip()
    )
    playables_root = (cfg.get("playables_root") or "").strip()
    sync_extracted_root = (cfg.get("sync_extracted_root") or "").strip()
    playable_urls = tuple(cfg.get("playable_base_urls") or ())
    data_root = (cfg.get("data_root") or "").strip()
    if not data_root:
        data_root = str(
            Path(settings.gamecenter_bridge_data_root).expanduser().resolve().parent
            / "bridges"
            / key
        )
    return RootedProjectBridgeConfig(
        provider_key=key,
        source_root=Path(cfg["source_root"]).expanduser().resolve(),
        extra_source_roots=extra_roots,
        data_root=Path(data_root).expanduser().resolve(),
        enabled=bool(cfg.get("enabled")),
        write_enabled=bool(cfg.get("write_enabled")),
        project_allowlist=_global_project_allowlist(cfg),
        readable_roots=("assets", "packages", "settings", "src", "extensions"),
        root_files={"project.json", "package.json", "tsconfig.json", "jsconfig.json"},
        text_extensions={
            ".ts", ".tsx", ".js", ".jsx", ".json", ".txt", ".md", ".xml", ".fnt",
            ".plist", ".meta", ".prefab", ".scene", ".fire", ".anim", ".effect", ".shader", ".css", ".html",
        },
        max_read_bytes=256 * 1024,
        max_list_entries=2000,
        build_command=str(cfg.get("build_command") or ""),
        build_timeout_seconds=int(cfg.get("build_timeout_seconds") or 1800),
        keep_builds=int(cfg.get("release_keep_builds") or 10),
        cocos_creator_bin=str(cfg.get("cocos_creator_bin") or "").strip(),
        publish_enabled=bool(cfg.get("publish_enabled")),
        playables_root=Path(playables_root).expanduser().resolve() if playables_root else None,
        sync_extracted_root=(
            Path(sync_extracted_root).expanduser().resolve() if sync_extracted_root else None
        ),
        playable_base_url=str(cfg.get("playable_base_url") or "").strip(),
        playable_base_urls=playable_urls,
        release_keep=int(cfg.get("release_keep") or 20),
    )


def create_configured_bridge_service(
    provider_key: str,
    cfg: dict[str, Any],
    *,
    project_allowlist_override: set[str] | None = None,
) -> RootedProjectBridgeService:
    key = (provider_key or "").strip().lower()
    merged = dict(cfg)
    allowlist = _group_allowlist_for_provider(
        key,
        project_allowlist_override=project_allowlist_override,
    )
    if allowlist is None:
        allowlist = _global_project_allowlist(merged)
    config = bridge_config_from_settings(key, merged)
    config.project_allowlist = allowlist
    return RootedProjectBridgeService(config)
