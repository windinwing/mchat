"""Workspace types for local (A) and container (B) tenant isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class WorkspaceMode(str, Enum):
    """Execution backend for a tenant workspace."""

    LOCAL = "local"
    CONTAINER = "container"


@dataclass(frozen=True)
class WorkspaceLimits:
    """Capability and quota limits derived from subscription plan."""

    shell_enabled: bool = False
    studio_enabled: bool = True
    max_disk_bytes: int | None = None


@dataclass
class WorkspaceContext:
    """Resolved tenant workspace for skill execution and studio memory."""

    user_id: str
    mode: WorkspaceMode
    tenant_root: Path
    limits: WorkspaceLimits
    customer_id: str | None = None
    channel_id: str | None = None
    container_name: str | None = None
    effective_mode: WorkspaceMode = field(default=WorkspaceMode.LOCAL)
    fallback_reason: str | None = None

    def uploads_dir(self) -> Path:
        return self.tenant_root / "uploads"

    def studio_dir(self, channel_id: str | None = None) -> Path:
        cid = channel_id or self.channel_id
        if not cid:
            return self.tenant_root / "studio"
        return self.tenant_root / "studio" / cid

    def skills_dir(self) -> Path:
        return self.tenant_root / "skills"

    def data_dir(self) -> Path:
        return self.tenant_root / "data"
