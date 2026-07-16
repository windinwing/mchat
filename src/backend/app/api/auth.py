"""Auth API router."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.middleware.auth import (
    get_current_user,
    get_user_permissions,
    require_permission,
    Permission,
)
from app.models.user import User
from app.schemas.auth import (
    BootstrapResponse,
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UpdateUserRequest,
    UserResponse,
)
from app.schemas.setup import SetupStatusResponse
from app.services.auth_service import AuthService, _UNSET
from app.services.setup_status_service import get_setup_status

router = APIRouter()


@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap_hint() -> BootstrapResponse:
    """Return default admin credentials hint when enabled (self-hosted dev).

    Also reports runtime edition flags (signup/cloud) so the frontend can show
    the correct login UI even when built with the wrong VITE_MCHAT_EDITION flag.
    """
    show = settings.show_bootstrap_credentials
    return BootstrapResponse(
        username=settings.admin_username,
        password=settings.admin_password if show else None,
        show_credentials=show,
        signup_enabled=settings.signup_enabled,
        cloud_edition=settings.cloud_mode,
    )


@router.get("/setup-status", response_model=SetupStatusResponse)
async def setup_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SetupStatusResponse:
    """First-run hints: AI provider and assistant configured."""
    return await get_setup_status(db, current_user)


@router.get("/permissions")
async def my_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Current user's effective permission codes (for UI gating)."""
    perms = await get_user_permissions(current_user, db)
    return {"permissions": sorted(perms)}


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate user and return JWT token."""
    auth_service = AuthService(db)
    try:
        result = await auth_service.login(request.username, request.password)
        return result
    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        if "can't connect" in err or "operationalerror" in err:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable. Run: make db-mysql-dev or make setup",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {e}",
        ) from e


@router.post("/register", response_model=TokenResponse)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register a new agent user."""
    auth_service = AuthService(db)
    try:
        result = await auth_service.register(
            username=request.username,
            password=request.password,
            display_name=request.display_name,
            avatar_url=request.avatar_url,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {e}",
        )



@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current authenticated user info."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Update current authenticated user profile."""
    auth_service = AuthService(db)
    fields = request.model_dump(exclude_unset=True)
    return await auth_service.update_profile(
        current_user,
        display_name=fields.get("display_name", _UNSET),
        avatar_url=fields.get("avatar_url", _UNSET),
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Change password for the current user."""
    auth_service = AuthService(db)
    await auth_service.change_password(
        current_user,
        request.current_password,
        request.new_password,
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    _admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    """List all users (admin only)."""
    auth_service = AuthService(db)
    return await auth_service.list_users()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    _admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Create a new user (admin only)."""
    auth_service = AuthService(db)
    return await auth_service.create_user(
        username=request.username,
        password=request.password,
        role=request.role,
        display_name=request.display_name,
        skill_ids=request.skill_ids,
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    _admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Update user role or reset password (admin only)."""
    auth_service = AuthService(db)
    fields = request.model_dump(exclude_unset=True)
    set_policy = "workspace_container_allowed" in fields
    set_skill_ids = "skill_ids" in fields
    if set_policy:
        fields.pop("workspace_container_allowed")
    if set_skill_ids:
        fields.pop("skill_ids")
    user = await auth_service.update_user(
        user_id,
        role=fields.get("role"),
        display_name=fields.get("display_name"),
        password=fields.get("password"),
        skill_ids=request.skill_ids,
        set_skill_ids=set_skill_ids,
        workspace_container_allowed=request.workspace_container_allowed,
        set_workspace_container_allowed=set_policy,
    )
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a user (admin only)."""
    auth_service = AuthService(db)
    await auth_service.delete_user(user_id, actor_id=admin.id)
