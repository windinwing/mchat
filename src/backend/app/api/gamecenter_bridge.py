"""Read-only GameCenter bridge API."""

from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import get_current_user
from app.models.user import User
from app.services.gamecenter_provider import create_gamecenter_bridge_service

router = APIRouter()


def _require_staff(user: User) -> User:
    if user.role not in {"admin", "agent"}:
        raise HTTPException(status_code=403, detail="Staff access required")
    return user


@router.get("/projects")
async def list_projects(current_user: User = Depends(get_current_user)):
    _require_staff(current_user)
    return create_gamecenter_bridge_service().list_projects()


@router.get("/projects/{slug}")
async def get_project(slug: str, current_user: User = Depends(get_current_user)):
    _require_staff(current_user)
    return create_gamecenter_bridge_service().get_project(slug)


@router.get("/projects/{slug}/files")
async def list_project_files(
    slug: str,
    path: str = "",
    current_user: User = Depends(get_current_user),
):
    _require_staff(current_user)
    return create_gamecenter_bridge_service().list_files(slug, path)


@router.get("/projects/{slug}/file")
async def read_project_file(
    slug: str,
    path: str,
    current_user: User = Depends(get_current_user),
):
    _require_staff(current_user)
    return create_gamecenter_bridge_service().read_file(slug, path)
