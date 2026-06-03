"""Request-scoped workspace context for skill execution."""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from typing import AsyncIterator

from app.workspace.types import WorkspaceContext

_current_workspace: ContextVar[WorkspaceContext | None] = ContextVar(
    "mchat_workspace", default=None
)


def get_workspace_context() -> WorkspaceContext | None:
    return _current_workspace.get()


def set_workspace_context(ctx: WorkspaceContext | None) -> Token:
    return _current_workspace.set(ctx)


def reset_workspace_context(token: Token) -> None:
    _current_workspace.reset(token)


@asynccontextmanager
async def workspace_execution_scope(
    ctx: WorkspaceContext | None,
) -> AsyncIterator[WorkspaceContext | None]:
    """Bind workspace context and ensure provider readiness for skill runs."""
    if ctx is None:
        yield None
        return

    from app.workspace.factory import get_workspace_provider

    provider = get_workspace_provider(ctx)
    ready = await provider.ensure_ready()
    token = set_workspace_context(ready)
    try:
        yield ready
    finally:
        reset_workspace_context(token)
