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


# ── Game center (metadata-enhanced project listing) ──


@router.get("/providers/{provider_key}/games")
async def list_provider_games(
    provider_key: str,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    """List all games with metadata from game.meta.json."""
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().list_games()


@router.get("/providers/{provider_key}/games/{slug}")
async def get_provider_game(
    provider_key: str,
    slug: str,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    """Single game detail with metadata."""
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().get_game(slug)


@router.patch("/providers/{provider_key}/games/{slug}/meta")
async def update_provider_game_meta(
    provider_key: str,
    slug: str,
    request: dict,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_WRITE)),
):
    """Update game.meta.json (name, category, description, etc.)."""
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().update_game_meta(slug, request)


# ── new generic development endpoints ──


@router.get("/providers/{provider_key}/projects/{slug}/search")
async def search_provider_project_files(
    provider_key: str,
    slug: str,
    q: str,
    path: str = "",
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().search_files(slug, q, path_hint=path)


@router.get("/providers/{provider_key}/projects/{slug}/changes/{change_id}/diff")
async def diff_provider_project_change(
    provider_key: str,
    slug: str,
    change_id: str,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_READ)),
):
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().diff_change(slug, change_id)


@router.post("/providers/{provider_key}/projects/create")
async def create_provider_project(
    provider_key: str,
    request: dict,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_WRITE)),
):
    slug = str(request.get("slug") or "").strip()
    template = str(request.get("template") or "cocos-empty").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().create_project(slug, template, provider_key=provider_key)


@router.post("/providers/{provider_key}/projects/{slug}/upload")
async def upload_provider_project_asset(
    provider_key: str,
    slug: str,
    request: dict,
    current_user: User = Depends(require_permission(Permission.DEVBRIDGE_WRITE)),
):
    path = str(request.get("path") or "").strip()
    data_b64 = str(request.get("data") or "")
    overwrite = bool(request.get("overwrite"))
    if not path or not data_b64:
        raise HTTPException(status_code=400, detail="path and data (base64) are required")
    provider = get_devbridge_provider(provider_key)
    return provider.service_factory().upload_asset(slug, path, data_b64, overwrite=overwrite)
