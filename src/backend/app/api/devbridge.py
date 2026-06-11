"""Generic development bridge API."""

from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import Permission, get_current_user, require_permission
from app.models.user import User
from app.schemas.devbridge import (
    DevBridgeBuildRequest,
    DevBridgePatchRequest,
    DevBridgePublishRequest,
    DevBridgeRollbackRequest,
)
from app.services.devbridge_registry import get_devbridge_provider, list_devbridge_providers

router = APIRouter()


@router.get("/providers")
async def list_providers(
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    return list_devbridge_providers()


@router.get("/providers/{provider_key}/projects")
async def list_provider_projects(
    provider_key: str,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().list_projects()


@router.get("/providers/{provider_key}/projects/{slug}")
async def get_provider_project(
    provider_key: str,
    slug: str,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().get_project(slug)


@router.get("/providers/{provider_key}/projects/{slug}/files")
async def list_provider_project_files(
    provider_key: str,
    slug: str,
    path: str = "",
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().list_files(slug, path)


@router.get("/providers/{provider_key}/projects/{slug}/file")
async def read_provider_project_file(
    provider_key: str,
    slug: str,
    path: str,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().read_file(slug, path)


@router.get("/providers/{provider_key}/projects/{slug}/changes")
async def list_provider_project_changes(
    provider_key: str,
    slug: str,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().list_changes(slug)


@router.post("/providers/{provider_key}/projects/{slug}/patch")
async def patch_provider_project_file(
    provider_key: str,
    slug: str,
    request: DevBridgePatchRequest,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_WRITE)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().patch_file(
        slug,
        request.path,
        content=request.content,
        actor_user_id=current_user.id,
        summary=request.summary,
    )


@router.post("/providers/{provider_key}/projects/{slug}/changes/{change_id}/revert")
async def revert_provider_project_change(
    provider_key: str,
    slug: str,
    change_id: str,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_WRITE)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().revert_change(slug, change_id, actor_user_id=current_user.id)


@router.post("/providers/{provider_key}/projects/{slug}/build")
async def build_provider_project(
    provider_key: str,
    slug: str,
    request: DevBridgeBuildRequest,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_WRITE)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().build_project(
        slug,
        actor_user_id=current_user.id,
        summary=request.summary,
    )


@router.get("/providers/{provider_key}/projects/{slug}/builds")
async def list_provider_project_builds(
    provider_key: str,
    slug: str,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().list_builds(slug)


@router.get("/providers/{provider_key}/projects/{slug}/releases")
async def list_provider_project_releases(
    provider_key: str,
    slug: str,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().list_releases(slug)


@router.post("/providers/{provider_key}/projects/{slug}/publish")
async def publish_provider_project_build(
    provider_key: str,
    slug: str,
    request: DevBridgePublishRequest,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_WRITE)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().publish_build(
        slug,
        request.build_id,
        actor_user_id=current_user.id,
        summary=request.summary,
    )


@router.post("/providers/{provider_key}/projects/{slug}/rollback")
async def rollback_provider_project_release(
    provider_key: str,
    slug: str,
    request: DevBridgeRollbackRequest,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_WRITE)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().rollback_release(
        slug,
        request.release_id,
        actor_user_id=current_user.id,
    )
