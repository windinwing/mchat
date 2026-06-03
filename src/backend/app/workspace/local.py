"""Local volume workspace provider (Plan A)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from app.workspace.paths import ensure_execution_layout, ensure_studio_layout
from app.workspace.types import WorkspaceContext, WorkspaceMode


class LocalWorkspaceProvider:
    def __init__(self, ctx: WorkspaceContext) -> None:
        self.ctx = ctx

    async def ensure_ready(self) -> WorkspaceContext:
        ensure_execution_layout(self.ctx.tenant_root)
        if self.ctx.limits.studio_enabled and self.ctx.channel_id:
            ensure_studio_layout(self.ctx.tenant_root, self.ctx.channel_id)
        self.ctx.effective_mode = WorkspaceMode.LOCAL
        return self.ctx

    def execution_env(self) -> dict[str, str]:
        uploads = self.ctx.uploads_dir()
        uploads.mkdir(parents=True, exist_ok=True)
        root = str(self.ctx.tenant_root)
        env = {
            "MCHAT_WORKSPACE_ROOT": root,
            "MCHAT_UPLOAD_DIR": str(uploads),
            "MCHAT_WORKSPACE_SKILLS_DIR": str(self.ctx.skills_dir()),
            "MCHAT_WORKSPACE_DATA_DIR": str(self.ctx.data_dir()),
            "MCHAT_WORKSPACE_MODE": self.ctx.effective_mode.value,
            "MCHAT_WORKSPACE_USER_ID": self.ctx.user_id,
        }
        if self.ctx.customer_id:
            env["MCHAT_WORKSPACE_CUSTOMER_ID"] = self.ctx.customer_id
        if self.ctx.channel_id:
            env["MCHAT_WORKSPACE_CHANNEL_ID"] = self.ctx.channel_id
        return env

    async def run_blocking(self, fn: Callable[[], Any]) -> Any:
        return await asyncio.to_thread(fn)
