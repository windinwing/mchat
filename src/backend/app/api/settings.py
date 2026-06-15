"""System settings and widget configuration API router."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.setting import Setting

from app.middleware.auth import (
    DEFAULT_ROLE_PERMISSIONS,
    Permission,
    require_permission,
)
from app.models.setting import Setting
from app.models.user import User
from app.models.customer import CustomerConfig
from app.schemas.agent import (
    CustomerConfigCreate,
    CustomerConfigResponse,
)

from app.schemas.settings import AppLogResponse, AppSettingsResponse, AppSettingsUpdate
from app.services.settings_service import SettingsService
from app.services.agent_service import AgentService

router = APIRouter()

# ─── System Settings ───────────────────────────────────────────

@router.get("", response_model=AppSettingsResponse)
async def get_settings(
    _admin: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Get current system settings."""
    service = SettingsService(db)
    return await service.get_settings()


@router.put("", response_model=AppSettingsResponse)
async def update_settings(
    request: AppSettingsUpdate,
    _admin: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update system settings."""
    service = SettingsService(db)
    return await service.update_settings(request)


class SettingKeyValue(BaseModel):
    key: str
    value: object


@router.get("/key-value/{key}")
async def get_setting_key(
    key: str,
    _admin: User = Depends(require_permission(Permission.SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get a single setting value by key."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"key": row.key, "value": row.value}


@router.put("/key-value")
async def update_setting_key(
    request: SettingKeyValue,
    _admin: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Upsert a single setting key with an arbitrary JSON value."""
    from sqlalchemy import select as sa_select
    result = await db.execute(sa_select(Setting).where(Setting.key == request.key))
    row = result.scalar_one_or_none()
    if row is None:
        row = Setting(key=request.key, value=request.value)
        db.add(row)
    else:
        row.value = request.value
    await db.commit()
    return {"ok": True}


class MilvusTestRequest(BaseModel):
    milvus_enabled: bool = False
    milvus_host: str = "localhost"
    milvus_port: int = Field(19530, ge=1, le=65535)


@router.post("/milvus/test")
async def test_milvus_settings(
    request: MilvusTestRequest,
    _admin: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Test Milvus connection with provided settings."""
    service = SettingsService(db)
    return await service.test_milvus_connection(
        enabled=request.milvus_enabled,
        host=request.milvus_host,
        port=request.milvus_port,
    )


class ElasticsearchTestRequest(BaseModel):
    elasticsearch_enabled: bool = False
    elasticsearch_url: str = ""


@router.post("/elasticsearch/test")
async def test_elasticsearch_settings(
    request: ElasticsearchTestRequest,
    _admin: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Test Elasticsearch connection with provided settings."""
    service = SettingsService(db)
    return await service.test_elasticsearch_connection(
        enabled=request.elasticsearch_enabled,
        url=request.elasticsearch_url,
    )


class TokenizerFileContent(BaseModel):
    content: str = ""


@router.get("/tokenizer")
async def list_tokenizer_files(
    _admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
):
    """List global tokenizer text files (stop words, suffix chars)."""
    from app.knowledge.tokenizer_files import list_global_tokenizer_files

    return list_global_tokenizer_files()


@router.get("/tokenizer/{file_key}")
async def read_tokenizer_file(
    file_key: str,
    _admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
):
    """Read a global tokenizer text file."""
    from app.knowledge.tokenizer_files import read_global_tokenizer_file

    try:
        return read_global_tokenizer_file(file_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/tokenizer/{file_key}")
async def write_tokenizer_file(
    file_key: str,
    request: TokenizerFileContent,
    _admin: User = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
):
    """Write a global tokenizer text file (one entry per line)."""
    from app.knowledge.bm25 import bm25_index
    from app.knowledge.tokenizer_files import write_global_tokenizer_file

    try:
        result = write_global_tokenizer_file(file_key, request.content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    bm25_index.invalidate_all()
    return result


@router.get("/logs", response_model=AppLogResponse)
async def get_backend_logs(
    source: str = "app",
    lines: int = 200,
    _admin: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Get backend log tail for admin troubleshooting."""
    source = source if source in ("app", "error") else "app"
    service = SettingsService(db)
    result = await service.get_log_tail(source=source, lines=lines)
    return AppLogResponse(**result)


# ─── Role Permissions ────────────────────────────────────────────


class RolePermissionsResponse(BaseModel):
    role_permissions: dict[str, list[str]]


@router.get("/role-permissions", response_model=RolePermissionsResponse)
async def get_role_permissions(
    _admin: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Get current role-to-permission mapping (from DB or defaults)."""
    result = await db.execute(
        select(Setting).where(Setting.key == "role_permissions")
    )
    row = result.scalar_one_or_none()
    if row:
        try:
            stored = json.loads(row.value)
            if isinstance(stored, dict):
                return RolePermissionsResponse(role_permissions=stored)
        except json.JSONDecodeError:
            pass
    return RolePermissionsResponse(
        role_permissions={k: list(v) for k, v in DEFAULT_ROLE_PERMISSIONS.items()}
    )


@router.put("/role-permissions", response_model=RolePermissionsResponse)
async def update_role_permissions(
    request: RolePermissionsResponse,
    _admin: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update role-to-permission mapping. Only valid permissions are kept."""
    valid_perms = set(Permission.all())
    sanitised: dict[str, list[str]] = {}
    for role, perms in request.role_permissions.items():
        if not isinstance(perms, list):
            continue
        sanitised[role] = [p for p in perms if p in valid_perms]

    result = await db.execute(
        select(Setting).where(Setting.key == "role_permissions")
    )
    existing = result.scalar_one_or_none()
    value_str = json.dumps(sanitised, ensure_ascii=False)
    if existing:
        existing.value = value_str
    else:
        db.add(Setting(key="role_permissions", value=value_str, category="general"))
    await db.flush()
    return RolePermissionsResponse(role_permissions=sanitised)


# ─── Widget / Customer Config ──────────────────────────────────

@router.get("/widget", response_model=CustomerConfigResponse)
async def get_widget_settings(
    admin: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Get the first customer (widget) config for the current user."""
    agent_service = AgentService(db)
    configs = await agent_service.list_customer_configs(user_id=admin.id)
    if not configs:
        # Return a default stub
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No widget config found. Please create one first.",
        )
    return configs[0]


@router.put("/widget", response_model=CustomerConfigResponse)
async def update_widget_settings(
    request: CustomerConfigCreate,
    admin: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the first widget config for the current user."""
    agent_service = AgentService(db)
    configs = await agent_service.list_customer_configs(user_id=admin.id)

    if configs:
        # Update existing
        updated = await agent_service.update_customer_config(
            config_id=configs[0].id,
            user_id=admin.id,
            data=request,
        )
        return updated or configs[0]
    else:
        # Create new
        return await agent_service.create_customer_config(
            user_id=admin.id, data=request
        )
