"""Agent management API router."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import has_global_scope, require_permission, Permission
from app.models.user import User
from app.schemas.agent import (
    AIConfigCreate,
    AIConfigResponse,
    AIConfigUpdate,
    ConnectionTestRequest,
    ConnectionTestResponse,
    CustomerConfigCreate,
    CustomerConfigResponse,
    ModelCatalogRequest,
    ModelCatalogResponse,
    UploadedAssetResponse,
)
from app.services.agent_service import AgentService
from app.services.llm_credentials import (
    ensure_ai_config_api_key,
    ensure_ai_config_endpoint_allowed,
    ensure_llm_endpoint_allowed,
)
from app.services.model_catalog import ConnectionParams, list_models, test_connection
from app.utils.chat_upload import save_chat_attachment

router = APIRouter()


@router.post("/ai-configs", response_model=AIConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_config(
    request: AIConfigCreate,
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new AI configuration."""
    service = AgentService(db)
    return await service.create_ai_config(user_id=admin.id, data=request)


@router.get("/ai-configs", response_model=list[AIConfigResponse])
async def list_ai_configs(
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """List all AI configurations for current user."""
    service = AgentService(db)
    return await service.list_ai_configs(user_id=admin.id)


@router.get("/ai-configs/{config_id}", response_model=AIConfigResponse)
async def get_ai_config(
    config_id: str,
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific AI configuration."""
    service = AgentService(db)
    config = await service.get_ai_config(
        config_id=config_id, user_id=admin.id
    )
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI config not found",
        )
    return config


@router.put("/ai-configs/{config_id}", response_model=AIConfigResponse)
async def update_ai_config(
    config_id: str,
    request: AIConfigUpdate,
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update an AI configuration."""
    service = AgentService(db)
    is_admin = await has_global_scope(admin, db)
    config = await service.update_ai_config(
        config_id=config_id, user_id=admin.id, data=request, is_admin=is_admin
    )
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI config not found",
        )
    return config


@router.post("/ai-configs/models", response_model=ModelCatalogResponse)
async def fetch_model_catalog(
    request: ModelCatalogRequest,
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """List models from provider API (OpenAI-compatible, Anthropic, Google)."""
    api_key = request.api_key
    provider = request.provider
    api_base = request.api_base
    stored_config = None
    if not api_key.strip() and request.config_id:
        service = AgentService(db)
        cfg = await service.get_ai_config_record(request.config_id, admin.id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="AI config not found")
        cfg = await ensure_ai_config_api_key(db, cfg)
        stored_config = cfg
        api_key = cfg.api_key
        # A stored credential may only be sent to its server-side connection
        # target. Never combine a shared secret with caller-controlled routing.
        provider = cfg.provider
        api_base = cfg.api_base
    if stored_config is not None:
        await ensure_ai_config_endpoint_allowed(db, stored_config)
    else:
        await ensure_llm_endpoint_allowed(
            db,
            user_id=admin.id,
            provider=provider,
            api_base=api_base,
        )
    models = await list_models(
        ConnectionParams(
            provider=provider,
            api_key=api_key,
            api_base=api_base,
        )
    )
    return ModelCatalogResponse(models=models)


@router.post("/ai-configs/test", response_model=ConnectionTestResponse)
async def test_ai_connection(
    request: ConnectionTestRequest,
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Send a minimal chat request to verify API credentials."""
    api_key = request.api_key
    api_base = request.api_base
    provider = request.provider
    model = request.model
    stored_config = None
    if request.config_id:
        service = AgentService(db)
        cfg = await service.get_ai_config_record(request.config_id, admin.id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="AI config not found")
        if not api_key.strip():
            cfg = await ensure_ai_config_api_key(db, cfg)
            api_key = cfg.api_key
            api_base = cfg.api_base
            provider = cfg.provider
            model = cfg.model
            stored_config = cfg
    if stored_config is not None:
        await ensure_ai_config_endpoint_allowed(db, stored_config)
    else:
        await ensure_llm_endpoint_allowed(
            db,
            user_id=admin.id,
            provider=provider,
            api_base=api_base,
        )
    ok, message = await test_connection(
        ConnectionParams(
            provider=provider,
            api_key=api_key,
            api_base=api_base,
        ),
        model=model,
    )
    return ConnectionTestResponse(ok=ok, message=message)


@router.delete("/ai-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_config(
    config_id: str,
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete an AI configuration."""
    service = AgentService(db)
    is_admin = await has_global_scope(admin, db)
    success = await service.delete_ai_config(
        config_id=config_id, user_id=admin.id, is_admin=is_admin
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI config not found",
        )
    return None


@router.post("/customer-configs", response_model=CustomerConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_customer_config(
    request: CustomerConfigCreate,
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new customer service configuration."""
    service = AgentService(db)
    return await service.create_customer_config(
        user_id=admin.id, data=request
    )


@router.get("/customer-configs", response_model=list[CustomerConfigResponse])
async def list_customer_configs(
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """List all customer configurations for current user."""
    service = AgentService(db)
    return await service.list_customer_configs(user_id=admin.id)


@router.put("/customer-configs/{config_id}", response_model=CustomerConfigResponse)
async def update_customer_config(
    config_id: str,
    request: CustomerConfigCreate,
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Update a customer configuration."""
    service = AgentService(db)
    config = await service.update_customer_config(
        config_id=config_id, user_id=admin.id, data=request
    )
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer config not found",
        )
    return config


@router.get("/customer-configs/{config_id}", response_model=CustomerConfigResponse)
async def get_customer_config(
    config_id: str,
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific customer configuration."""
    service = AgentService(db)
    config = await service.get_customer_config(
        config_id=config_id, user_id=admin.id
    )
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer config not found",
        )
    return config


@router.post(
    "/customer-configs/upload-asset",
    response_model=UploadedAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_customer_config_asset(
    file: UploadFile = File(...),
    admin: User = Depends(require_permission(Permission.AGENTS_WRITE)),
):
    """Upload an asset that can be attached by customer-config auto replies."""
    del admin
    attachment = await save_chat_attachment(file)
    mime = str(attachment.get("mime") or "")
    asset_type = "video" if mime.startswith("video/") else "image" if mime.startswith("image/") else "file"
    return UploadedAssetResponse(
        url=str(attachment["url"]),
        name=str(attachment["name"]),
        mime=mime,
        size=int(attachment.get("size") or 0),
        type=asset_type,
    )
