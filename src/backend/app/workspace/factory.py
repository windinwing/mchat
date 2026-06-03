"""Workspace provider factory."""

from __future__ import annotations

from app.workspace.container import ContainerWorkspaceProvider
from app.workspace.local import LocalWorkspaceProvider
from app.workspace.types import WorkspaceContext, WorkspaceMode


def get_workspace_provider(ctx: WorkspaceContext) -> LocalWorkspaceProvider:
    if ctx.mode == WorkspaceMode.CONTAINER:
        return ContainerWorkspaceProvider(ctx)
    return LocalWorkspaceProvider(ctx)
