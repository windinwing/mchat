"""Skill management API router."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import require_permission, Permission
from app.models.user import User
from app.schemas.skill import (
    SkillCacheRefreshResponse,
    SkillCacheStatusResponse,
    SkillCatalogResponse,
    SkillCreate,
    SkillInstallUrlRequest,
    SkillResponse,
    SkillUpdate,
)
from app.services.skill_service import SkillService

router = APIRouter()


class SkillCapabilitiesResponse(BaseModel):
    tenant_skill_authoring: bool = False
    container_entitled: bool = False
    platform_skill_editing: bool = False


@router.get("/capabilities", response_model=SkillCapabilitiesResponse)
async def skill_capabilities(
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Whether current user may create/edit tenant skills (container workspace)."""
    from app.middleware.auth import has_global_scope
    from app.workspace.skill_policy import (
        user_container_entitled,
        user_may_author_tenant_skills,
    )

    entitled = await user_container_entitled(db, admin.id)
    return SkillCapabilitiesResponse(
        tenant_skill_authoring=await user_may_author_tenant_skills(db, admin.id),
        container_entitled=entitled,
        platform_skill_editing=await has_global_scope(admin, db),
    )


@router.get("", response_model=list[SkillResponse])
async def list_skills(
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List all skills for current user."""
    service = SkillService(db)
    return await service.list_skills(user_id=admin.id)


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    request: SkillCreate,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new skill directory with a minimal SKILL.md."""
    service = SkillService(db)
    return await service.create_skill(
        user_id=admin.id,
        name=request.name,
        description=request.description,
        skill_type=request.skill_type,
    )


@router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    request: SkillUpdate,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable a skill, or update its config."""
    service = SkillService(db)
    skill = await service.update_skill(
        skill_id=skill_id, user_id=admin.id, data=request
    )
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill not found",
        )
    return skill


@router.post("/{skill_id}/refresh-cache", response_model=SkillResponse)
async def refresh_skill_cache(
    skill_id: str,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Reload one skill's DB cache (path, prompt_body) from disk."""
    service = SkillService(db)
    skill = await service.refresh_skill_cache(skill_id=skill_id, user_id=admin.id)
    await db.commit()
    return skill


@router.post("/reload")
async def reload_skills(
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Reload skills from filesystem."""
    service = SkillService(db)
    return await service.reload_skills(user_id=admin.id)


@router.get("/cache-status", response_model=SkillCacheStatusResponse)
async def skill_cache_status(
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List DB vs disk cache drift for each skill."""
    service = SkillService(db)
    return await service.list_cache_status(user_id=admin.id)


@router.post("/cache/refresh-stale", response_model=SkillCacheRefreshResponse)
async def refresh_stale_skill_caches(
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Refresh prompt_body/path from disk for all stale skills."""
    service = SkillService(db)
    result = await service.refresh_stale_caches(user_id=admin.id)
    await db.commit()
    return result


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: str,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a skill."""
    service = SkillService(db)
    success = await service.delete_skill(
        skill_id=skill_id, user_id=admin.id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill not found",
        )
    return None


@router.post("/upload")
async def upload_skill(
    file: UploadFile,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Upload a new skill (zip file)."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .zip files are supported",
        )
    service = SkillService(db)
    try:
        return await service.upload_skill(
            user_id=admin.id, file=file
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload failed: {e}",
        ) from e


@router.post("/install-url", response_model=SkillResponse)
async def install_skill_from_url(
    request: SkillInstallUrlRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Install a skill package from direct URL or ClawHub skill name."""
    service = SkillService(db)
    source = request.url.strip()
    if source.startswith(("http://", "https://")):
        return await service.install_skill_from_url(
            user_id=admin.id,
            url=source,
            name_hint=request.name,
        )
    return await service.install_skill_by_name(
        user_id=admin.id,
        name=source,
    )


@router.get("/catalog", response_model=SkillCatalogResponse)
async def list_skill_catalog(
    query: str | None = None,
    limit: int = 24,
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Browse remote skill catalog (best-effort ClawHub integration)."""
    service = SkillService(db)
    items = await service.fetch_clawhub_catalog(query=query, limit=limit)
    return SkillCatalogResponse(source="clawhub", items=items)


# ── Skill file browser & editor ──────────────────────────────────


@router.get("/{skill_id}/files")
async def list_skill_files(
    skill_id: str,
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List all files in a skill directory."""
    service = SkillService(db)
    return await service.list_skill_files(skill_id=skill_id, user_id=admin.id)


@router.post("/{skill_id}/files")
async def upload_skill_file(
    skill_id: str,
    file: UploadFile = File(...),
    path: str = Form(""),
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file into a skill directory."""
    service = SkillService(db)
    return await service.upload_skill_file(
        skill_id=skill_id, user_id=admin.id, file=file, relative_path=path,
    )


@router.get("/{skill_id}/files/{file_path:path}")
async def read_skill_file(
    skill_id: str,
    file_path: str,
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Read a text file from a skill directory."""
    service = SkillService(db)
    return await service.read_skill_file(skill_id=skill_id, user_id=admin.id, file_path=file_path)


class WriteSkillFileRequest(BaseModel):
    content: str


@router.put("/{skill_id}/files/{file_path:path}")
async def write_skill_file(
    skill_id: str,
    file_path: str,
    request: WriteSkillFileRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Write content to a text file in a skill directory."""
    service = SkillService(db)
    return await service.write_skill_file(
        skill_id=skill_id, user_id=admin.id, file_path=file_path, content=request.content,
    )
