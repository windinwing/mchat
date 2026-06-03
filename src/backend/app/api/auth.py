"""Auth API router."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.middleware.auth import get_current_user, require_permission, Permission
from app.models.user import User
from app.schemas.auth import (
    BootstrapResponse,
    ChangePasswordRequest,
    SetPasswordRequest,
    CreateUserRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateUserRequest,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap_hint() -> BootstrapResponse:
    """Return default admin credentials hint when enabled (self-hosted dev)."""
    show = settings.show_bootstrap_credentials
    return BootstrapResponse(
        username=settings.admin_username,
        password=settings.admin_password if show else None,
        show_credentials=show,
    )


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
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Get current authenticated user info."""
    return AuthService(db).user_response(current_user)


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


@router.post("/set-password", status_code=status.HTTP_204_NO_CONTENT)
async def set_password(
    request: SetPasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Set password (portal phone users without current; admin still needs current)."""
    auth_service = AuthService(db)
    await auth_service.set_password(
        current_user,
        request.new_password,
        request.current_password,
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
    return await auth_service.update_user(
        user_id,
        role=request.role,
        display_name=request.display_name,
        password=request.password,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    admin: User = Depends(require_permission(Permission.USERS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a user (admin only)."""
    auth_service = AuthService(db)
    await auth_service.delete_user(user_id, actor_id=admin.id)
