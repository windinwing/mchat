"""Workspace API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkspaceStatusResponse(BaseModel):
    user_id: str
    customer_id: str | None = None
    channel_id: str | None = None
    mode: str = Field(description="Requested mode: local | container")
    effective_mode: str = Field(description="Actual mode after fallback")
    fallback_reason: str | None = None
    tenant_root: str
    uploads_dir: str
    container_name: str | None = None
    limits: dict[str, Any]
    execution_env: dict[str, str]
