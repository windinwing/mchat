"""Workspace status and admin APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.middleware.auth import get_current_user, has_global_scope, security_scheme
from app.models.customer import CustomerConfig
from app.models.user import User
from app.schemas.tenant_files import (
    TenantFileListResponse,
    TenantFileUploadResponse,
)
from app.schemas.workspace import (
    ChannelWorkspaceSummary,
    SidecarListItem,
    SidecarRecycleResponse,
    SidecarStatusResponse,
    UserWorkspaceSummary,
    UserWorkspaceUpdate,
    WorkspaceModeUpdate,
    WorkspaceStatusResponse,
)
from app.services.tenant_files_service import TenantFilesService
from app.workspace.admin_service import (
    list_channel_summaries,
    list_sidecar_items,
    list_user_workspace_summaries,
    recycle_user_sidecar,
    summarize_channel,
    update_channel_workspace_mode,
    update_user_workspace_settings,
)
from app.workspace.context import workspace_execution_scope
from app.workspace.disk_usage import tenant_execution_usage_bytes
from app.workspace.factory import get_workspace_provider
from app.workspace.resolver import build_workspace_context
from app.workspace.sidecar import sidecar_inspect
from app.workspace.sidecar_lifecycle import recycle_idle_sidecars
from app.workspace.usage_service import refresh_customer_storage_usage

router = APIRouter()


@router.get("/status", response_model=WorkspaceStatusResponse)
async def get_workspace_status(
    customer_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceStatusResponse:
    """Return resolved workspace mode, sidecar state, disk usage, and execution env."""
    customer_config: CustomerConfig | None = None
    channel_id: str | None = None
    if customer_id:
        result = await db.execute(
            select(CustomerConfig).where(CustomerConfig.id == customer_id)
        )
        customer_config = result.scalar_one_or_none()
        if customer_config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Channel not found",
            )
        if customer_config.user_id != current_user.id and not await has_global_scope(
            current_user, db
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to inspect this channel workspace",
            )
        channel_id = customer_config.id

    if customer_config is None:
        from app.workspace.automation_context import build_automation_workspace_context

        ctx = await build_automation_workspace_context(db, current_user.id)
    else:
        tenant_user_id = customer_config.user_id
        owner = await db.get(User, tenant_user_id)
        ctx = build_workspace_context(
            tenant_user_id,
            customer_config=customer_config,
            channel_id=channel_id,
            user_container_allowed=(
                owner.workspace_container_allowed if owner is not None else None
            ),
        )
    async with workspace_execution_scope(ctx) as ready:
        assert ready is not None
        provider = get_workspace_provider(ready)
        sidecar_raw = sidecar_inspect(ready.container_name)
        usage_synced = await refresh_customer_storage_usage(db, ready.user_id)
        await db.commit()
        return WorkspaceStatusResponse(
            user_id=ready.user_id,
            customer_id=ready.customer_id,
            channel_id=ready.channel_id,
            mode=ready.mode.value,
            effective_mode=ready.effective_mode.value,
            fallback_reason=ready.fallback_reason,
            tenant_root=str(ready.tenant_root),
            uploads_dir=str(ready.uploads_dir()),
            skills_dir=str(ready.skills_dir()),
            data_dir=str(ready.data_dir()),
            container_name=ready.container_name,
            sidecar=SidecarStatusResponse(**sidecar_raw),
            disk_usage_bytes=tenant_execution_usage_bytes(ready.tenant_root),
            usage_storage_bytes=usage_synced,
            limits={
                "shell_enabled": ready.limits.shell_enabled,
                "studio_enabled": ready.limits.studio_enabled,
                "max_disk_bytes": ready.limits.max_disk_bytes,
            },
            execution_env=provider.execution_env(),
        )


@router.get("/channels", response_model=list[ChannelWorkspaceSummary])
async def list_workspace_channels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChannelWorkspaceSummary]:
    """List workspace execution summary per customer agent (no sidecar auto-start)."""
    is_admin = await has_global_scope(current_user, db)
    user_filter = None if is_admin else current_user.id
    return await list_channel_summaries(db, user_id=user_filter)


@router.patch("/channels/{customer_id}", response_model=ChannelWorkspaceSummary)
async def patch_channel_workspace_mode(
    customer_id: str,
    body: WorkspaceModeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelWorkspaceSummary:
    """Assign local or container execution for a customer agent."""
    is_admin = await has_global_scope(current_user, db)
    try:
        summary = await update_channel_workspace_mode(
            db,
            customer_id=customer_id,
            user_id=current_user.id,
            workspace_mode=body.workspace_mode,
            is_admin=is_admin,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    await db.commit()
    return summary


@router.get("/sidecars", response_model=list[SidecarListItem])
async def list_workspace_sidecars(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SidecarListItem]:
    """List Docker execution sidecars (admin: all; tenant: own user_id only)."""
    items = list_sidecar_items()
    if await has_global_scope(current_user, db):
        return items
    return [item for item in items if item.user_id == current_user.id]


@router.post("/sidecars/{user_id}/recycle", response_model=SidecarRecycleResponse)
async def recycle_sidecar_for_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SidecarRecycleResponse:
    """Remove a user's sidecar container (next execution recreates if needed)."""
    is_admin = await has_global_scope(current_user, db)
    if user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    ok = recycle_user_sidecar(user_id)
    return SidecarRecycleResponse(
        ok=ok,
        removed=1 if ok else 0,
        message="Sidecar removed" if ok else "No sidecar to remove",
    )


@router.post("/sidecars/recycle-idle", response_model=SidecarRecycleResponse)
async def recycle_idle_sidecars_now(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SidecarRecycleResponse:
    """Manually run idle sidecar recycle (admin only)."""
    if not await has_global_scope(current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    removed = recycle_idle_sidecars()
    return SidecarRecycleResponse(
        ok=True,
        removed=removed,
        message=f"Recycled {removed} idle sidecar(s)",
    )


# ── Tenant file browser (uploads/) ───────────────────────────────


@router.get("/files", response_model=TenantFileListResponse)
async def list_tenant_files(
    subdir: str = "user",
    current_user: User = Depends(get_current_user),
) -> TenantFileListResponse:
    """List files under tenant uploads/ (default: uploads/user/)."""
    service = TenantFilesService()
    items = service.list_files(current_user.id, subdir=subdir)
    return TenantFileListResponse(subdir=subdir, items=items, total=len(items))


@router.post("/files/upload", response_model=TenantFileUploadResponse)
async def upload_tenant_file(
    file: UploadFile = File(...),
    subdir: str = Form("user"),
    relative_dir: str = Form(""),
    current_user: User = Depends(get_current_user),
) -> TenantFileUploadResponse:
    service = TenantFilesService()
    return await service.upload_file(
        current_user.id,
        file,
        subdir=subdir,
        relative_dir=relative_dir,
    )


@router.get("/files/download")
async def download_tenant_file(
    path: str,
    subdir: str = "user",
    uid: str | None = None,
    exp: int | None = None,
    sig: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Download a tenant file.

    Two access modes:
    - **Authenticated**: Bearer token → owner is the logged-in user.
    - **Signed URL**: ``uid`` + ``exp`` + ``sig`` params, so browser
      ``<img>``/``<video>`` tags can load chat attachments without an
      Authorization header. The signature binds (uid, subdir, path, exp).
    """
    from app.utils.upload_tokens import verify_workspace_token

    user_id: str | None = None

    # 1) Signed-URL access (no auth header needed)
    if exp is not None and sig and uid:
        if verify_workspace_token(uid, subdir, path, exp, sig):
            user_id = uid
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature"
            )

    # 2) Bearer-token access
    if user_id is None:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        from jose import JWTError

        from app.core.security import verify_access_token

        try:
            payload = verify_access_token(credentials.credentials)
            token_uid = payload.get("sub")
            if not token_uid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload",
                )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        result = await db.execute(select(User).where(User.id == token_uid))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
            )
        user_id = user.id

    service = TenantFilesService()
    target, mime = service.read_file(user_id, subdir=subdir, path=path)
    return FileResponse(target, media_type=mime, filename=target.name)


@router.delete("/files", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant_file(
    path: str,
    subdir: str = "user",
    current_user: User = Depends(get_current_user),
):
    service = TenantFilesService()
    service.delete_path(current_user.id, subdir=subdir, path=path)
    return None


class MkdirRequest(BaseModel):
    subdir: str = "user"
    name: str


@router.post("/files/mkdir", status_code=status.HTTP_201_CREATED)
async def create_tenant_directory(
    request: MkdirRequest,
    current_user: User = Depends(get_current_user),
):
    service = TenantFilesService()
    dir_path = service.mkdir(current_user.id, subdir=request.subdir, name=request.name)
    return {"path": dir_path}


@router.get("/users", response_model=list[UserWorkspaceSummary])
async def list_workspace_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserWorkspaceSummary]:
    """Admin: per-user container entitlement, sidecar status, and resource limits."""
    if not await has_global_scope(current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return await list_user_workspace_summaries(db)


@router.patch("/users/{user_id}", response_model=UserWorkspaceSummary)
async def patch_workspace_user(
    user_id: str,
    body: UserWorkspaceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserWorkspaceSummary:
    """Admin: update container policy and sidecar memory/CPU for a user."""
    if not await has_global_scope(current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    fields = body.model_dump(exclude_unset=True)
    user = await update_user_workspace_settings(
        db,
        user_id=user_id,
        workspace_container_allowed=body.workspace_container_allowed,
        set_container_allowed="workspace_container_allowed" in fields,
        workspace_sidecar_memory=body.workspace_sidecar_memory,
        workspace_sidecar_cpus=body.workspace_sidecar_cpus,
        set_sidecar_memory="workspace_sidecar_memory" in fields,
        set_sidecar_cpus="workspace_sidecar_cpus" in fields,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.commit()
    items = await list_user_workspace_summaries(db)
    for item in items:
        if item.user_id == user_id:
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.get("/settings/runtime")
async def workspace_runtime_settings(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Expose non-secret workspace container settings for admin UI."""
    return {
        "workspace_container_enabled": settings.workspace_container_enabled,
        "workspace_container_image": settings.workspace_container_image,
        "workspace_container_memory": settings.workspace_container_memory,
        "workspace_container_cpus": settings.workspace_container_cpus,
        "workspace_sidecar_idle_minutes": settings.workspace_sidecar_idle_minutes,
        "workspace_sidecar_recycle_enabled": settings.workspace_sidecar_recycle_enabled,
    }
