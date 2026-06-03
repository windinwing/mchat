"""Workspace API schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SidecarStatusResponse(BaseModel):
    exists: bool = False
    running: bool = False
    status: str | None = None
    started_at: str | None = None
    image: str | None = None
    error: str | None = None


class WorkspaceStatusResponse(BaseModel):
    user_id: str
    customer_id: str | None = None
    channel_id: str | None = None
    mode: str = Field(description="Requested mode: local | container")
    effective_mode: str = Field(description="Actual mode after fallback")
    fallback_reason: str | None = None
    tenant_root: str
    uploads_dir: str
    skills_dir: str
    data_dir: str
    container_name: str | None = None
    sidecar: SidecarStatusResponse | None = None
    disk_usage_bytes: dict[str, int] = Field(default_factory=dict)
    usage_storage_bytes: int | None = Field(
        default=None,
        description="Synced to customer_configs.usage_storage_bytes for this user",
    )
    limits: dict[str, Any]
    execution_env: dict[str, str]


class ChannelWorkspaceSummary(BaseModel):
    customer_id: str
    customer_name: str
    user_id: str
    plan: str
    workspace_mode: str | None = Field(
        None, description="Override: local | container; null = follow plan/default"
    )
    requested_mode: str
    effective_mode: str
    fallback_reason: str | None = None
    container_name: str | None = None
    sidecar: SidecarStatusResponse
    disk_usage_bytes: dict[str, int] = Field(default_factory=dict)
    usage_storage_bytes: int = 0
    last_active_at: str | None = None
    idle_minutes: int | None = None
    limits: dict[str, Any] = Field(default_factory=dict)


class SidecarListItem(BaseModel):
    container_name: str
    container_id: str = ""
    user_id: str = ""
    running: bool = False
    status: str = ""
    image: str = ""
    configured_image: str = ""
    image_matches: bool = True
    started_at: str | None = None
    last_active_at: str | None = None
    idle_minutes: int | None = None


class WorkspaceModeUpdate(BaseModel):
    workspace_mode: Literal["local", "container"] | None = Field(
        None,
        description="Set local/container override; null clears override (auto from plan)",
    )


class SidecarRecycleResponse(BaseModel):
    ok: bool
    removed: int = 0
    message: str = ""
