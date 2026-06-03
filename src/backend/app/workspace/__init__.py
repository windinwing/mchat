"""Unified tenant workspace (Plan A local + Plan B container)."""

from app.workspace.context import (
    get_workspace_context,
    reset_workspace_context,
    set_workspace_context,
    workspace_execution_scope,
)
from app.workspace.paths import (
    resolve_studio_path,
    resolve_workspace_root,
    safe_workspace_segment,
    tenant_studio_dir,
)
from app.workspace.resolver import (
    build_workspace_context,
    resolve_workspace_mode,
    workspace_user_id_for_chat,
    workspace_user_id_for_execution,
)
from app.workspace.types import WorkspaceContext, WorkspaceLimits, WorkspaceMode

__all__ = [
    "WorkspaceContext",
    "WorkspaceLimits",
    "WorkspaceMode",
    "build_workspace_context",
    "get_workspace_context",
    "resolve_studio_path",
    "resolve_workspace_mode",
    "resolve_workspace_root",
    "reset_workspace_context",
    "safe_workspace_segment",
    "set_workspace_context",
    "tenant_studio_dir",
    "workspace_execution_scope",
    "workspace_user_id_for_chat",
    "workspace_user_id_for_execution",
]
