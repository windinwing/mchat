"""Admin template management API — CRUD for channel templates."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import get_current_admin
from app.models.user import User
from app.models.channel_template import ChannelTemplate
from app.services.skill_filter import filter_skill_ids_global

router = APIRouter()


async def _sanitize_template_payload(
    db: AsyncSession, payload: dict
) -> dict:
    if "default_skill_ids" in payload and payload["default_skill_ids"] is not None:
        payload["default_skill_ids"] = await filter_skill_ids_global(
            db, payload["default_skill_ids"]
        )
    return payload


class TemplateUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    category: str | None = Field(None, max_length=50)
    icon: str | None = Field(None, max_length=100)
    price_monthly_cents: int | None = None
    price_yearly_cents: int | None = None
    trial_days: int | None = None
    is_published: bool | None = None
    sort_order: int | None = None
    default_ai_config_id: str | None = None
    default_ai_config_spec: dict | None = None
    default_skill_ids: list | None = None
    default_knowledge_base_ids: list | None = None
    default_knowledge_base_spec: dict | None = None
    default_theme: dict | None = None
    default_welcome_message: str | None = None
    default_offline_message: str | None = None
    max_publishing_accounts: int | None = None


@router.get("/admin/templates")
async def list_templates(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all templates (including unpublished)."""
    result = await db.execute(
        select(ChannelTemplate).order_by(ChannelTemplate.sort_order)
    )
    templates = result.scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "icon": t.icon,
            "price_monthly_cents": t.price_monthly_cents,
            "price_yearly_cents": t.price_yearly_cents,
            "trial_days": t.trial_days,
            "is_published": t.is_published,
            "sort_order": t.sort_order,
            "default_ai_config_id": t.default_ai_config_id,
            "default_ai_config_spec": t.default_ai_config_spec,
            "default_skill_ids": t.default_skill_ids,
            "default_knowledge_base_ids": t.default_knowledge_base_ids,
            "default_knowledge_base_spec": t.default_knowledge_base_spec,
            "default_theme": t.default_theme,
            "default_welcome_message": t.default_welcome_message,
            "default_offline_message": t.default_offline_message,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        }
        for t in templates
    ]


@router.get("/admin/templates/{template_id}")
async def get_template(
    template_id: str,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChannelTemplate).where(ChannelTemplate.id == template_id)
    )
    t = result.scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return {
        "id": t.id, "name": t.name, "description": t.description,
        "category": t.category, "icon": t.icon,
        "price_monthly_cents": t.price_monthly_cents,
        "price_yearly_cents": t.price_yearly_cents,
        "trial_days": t.trial_days,
        "is_published": t.is_published, "sort_order": t.sort_order,
        "default_ai_config_spec": t.default_ai_config_spec,
        "default_skill_ids": t.default_skill_ids,
        "default_knowledge_base_ids": t.default_knowledge_base_ids,
        "default_knowledge_base_spec": t.default_knowledge_base_spec,
        "default_theme": t.default_theme,
        "default_welcome_message": t.default_welcome_message,
        "default_offline_message": t.default_offline_message,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


@router.put("/admin/templates/{template_id}")
async def update_template(
    template_id: str,
    data: TemplateUpdate,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChannelTemplate).where(ChannelTemplate.id == template_id)
    )
    t = result.scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")

    update = await _sanitize_template_payload(
        db, data.model_dump(exclude_unset=True)
    )
    for key, value in update.items():
        setattr(t, key, value)
    await db.flush()
    await db.refresh(t)
    return {"ok": True, "id": t.id}


@router.post("/admin/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateUpdate,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    payload = await _sanitize_template_payload(db, data.model_dump())
    t = ChannelTemplate(
        name=payload.get("name") or data.name or "New Template",
        description=data.description,
        category=data.category or "customer_service",
        icon=data.icon,
        price_monthly_cents=data.price_monthly_cents or 0,
        price_yearly_cents=data.price_yearly_cents or 0,
        trial_days=data.trial_days or 14,
        is_published=data.is_published or False,
        sort_order=data.sort_order or 0,
        default_ai_config_id=data.default_ai_config_id,
        default_ai_config_spec=data.default_ai_config_spec,
        default_skill_ids=payload.get("default_skill_ids", data.default_skill_ids),
        default_knowledge_base_ids=data.default_knowledge_base_ids,
        default_knowledge_base_spec=data.default_knowledge_base_spec,
        default_theme=data.default_theme,
        default_welcome_message=data.default_welcome_message,
        default_offline_message=data.default_offline_message,
        max_publishing_accounts=data.max_publishing_accounts or 0,
    )
    db.add(t)
    await db.flush()
    await db.refresh(t)
    return {"ok": True, "id": t.id}


@router.delete("/admin/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChannelTemplate).where(ChannelTemplate.id == template_id)
    )
    t = result.scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(t)
    await db.flush()
