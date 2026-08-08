"""JWT auth dependency middleware with role-based permissions."""

from collections.abc import Callable
import json
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_access_token
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)

# ── Permissions ──────────────────────────────────────────────────

class Permission:
    """Permission constants for granular access control."""

    # User management
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"

    # Conversations
    CONVERSATIONS_READ = "conversations:read"
    CONVERSATIONS_WRITE = "conversations:write"

    # Knowledge base
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"

    # Skills
    SKILLS_READ = "skills:read"
    SKILLS_WRITE = "skills:write"

    # Agent / AI config
    AGENTS_READ = "agents:read"
    AGENTS_WRITE = "agents:write"

    # System settings
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"

    # Channels
    CHANNELS_READ = "channels:read"
    CHANNELS_WRITE = "channels:write"

    # Dashboard & stats
    DASHBOARD_READ = "dashboard:read"

    # Speech
    SPEECH_READ = "speech:read"
    SPEECH_WRITE = "speech:write"

    # DevBridge (project browse vs config are separate)
    DEVBRIDGE_READ = "devbridge:read"
    DEVBRIDGE_WRITE = "devbridge:write"
    DEVBRIDGE_SETTINGS_READ = "devbridge:settings:read"
    DEVBRIDGE_SETTINGS_WRITE = "devbridge:settings:write"

    @classmethod
    def all(cls) -> list[str]:
        # Include multi-segment keys like devbridge:settings:read (two colons).
        return [
            v
            for k, v in vars(cls).items()
            if k.isupper() and isinstance(v, str) and ":" in v
        ]


# ── Default Role → Permission mapping (fallback) ─────────────────

DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": Permission.all(),
    "agent": [
        Permission.CONVERSATIONS_READ,
        Permission.CONVERSATIONS_WRITE,
        Permission.KNOWLEDGE_READ,
        Permission.SKILLS_READ,
        Permission.SKILLS_WRITE,
        Permission.AGENTS_READ,
        Permission.AGENTS_WRITE,
        Permission.DASHBOARD_READ,
        Permission.SPEECH_READ,
        Permission.SPEECH_WRITE,
        Permission.CHANNELS_READ,
        Permission.DEVBRIDGE_READ,
    ],
    "user": [
        Permission.CONVERSATIONS_READ,
        Permission.CONVERSATIONS_WRITE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.SKILLS_READ,
        Permission.SKILLS_WRITE,
        Permission.AGENTS_READ,
        Permission.AGENTS_WRITE,
        Permission.DASHBOARD_READ,
        Permission.SPEECH_READ,
        Permission.SPEECH_WRITE,
    ],
    # 推广者：在 user 基础上增加发布账号 / 发送记录（内容分发用）。
    "promoter": [
        Permission.CONVERSATIONS_READ,
        Permission.CONVERSATIONS_WRITE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.SKILLS_READ,
        Permission.SKILLS_WRITE,
        Permission.AGENTS_READ,
        Permission.AGENTS_WRITE,
        Permission.DASHBOARD_READ,
        Permission.SPEECH_READ,
        Permission.SPEECH_WRITE,
        Permission.CHANNELS_READ,
        Permission.CHANNELS_WRITE,
    ],
}

# Portal tenant accounts always need these (even if role_permissions in DB is stale).
_PORTAL_TENANT_MIN_PERMISSIONS: frozenset[str] = frozenset(
    DEFAULT_ROLE_PERMISSIONS["user"]
)


async def load_role_permissions(db: AsyncSession) -> dict[str, list[str]]:
    """Load role-permission mapping from DB settings, falling back to defaults."""
    from app.models.setting import Setting

    try:
        result = await db.execute(
            select(Setting).where(Setting.key == "role_permissions")
        )
        row = result.scalar_one_or_none()
        if row:
            stored = json.loads(row.value)
            if isinstance(stored, dict):
                return {k: v for k, v in stored.items() if isinstance(v, list)}
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to load role_permissions from settings: {e}")

    return {k: list(v) for k, v in DEFAULT_ROLE_PERMISSIONS.items()}


async def get_user_permissions(user: User, db: AsyncSession | None = None) -> set[str]:
    """Get permissions for a user, loading role mapping from DB if session provided."""
    if db:
        role_perms = await load_role_permissions(db)
    else:
        role_perms = {k: list(v) for k, v in DEFAULT_ROLE_PERMISSIONS.items()}
    perms = set(role_perms.get(user.role, []))
    if user.role == "admin":
        perms.update(Permission.all())
        perms.update(
            {
                Permission.DEVBRIDGE_READ,
                Permission.DEVBRIDGE_WRITE,
                Permission.DEVBRIDGE_SETTINGS_READ,
                Permission.DEVBRIDGE_SETTINGS_WRITE,
            }
        )
    if user.role in ("user", "promoter"):
        perms.update(_PORTAL_TENANT_MIN_PERMISSIONS)
    return perms


async def user_has_permission(user: User, permission: str, db: AsyncSession | None = None) -> bool:
    """Check if a user has a specific permission."""
    perms = await get_user_permissions(user, db)
    return permission in perms


async def has_global_scope(user: User, db: AsyncSession) -> bool:
    """Return True if the user can see all data (has users:read permission)."""
    return await user_has_permission(user, Permission.USERS_READ, db)


# ── Auth dependencies ────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT Bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = verify_access_token(token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require admin role (backwards-compatible shortcut)."""
    if not await user_has_permission(current_user, Permission.SETTINGS_WRITE, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


async def get_current_agent(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require agent or admin role (backwards-compatible shortcut)."""
    if current_user.role not in ("admin", "agent"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent or admin privileges required",
        )
    return current_user


def require_permission(permission: str) -> Callable[..., Any]:
    """Factory: create a FastAPI dependency that requires a specific permission.

    Usage:
        @router.get("/users")
        async def list_users(
            admin: User = Depends(require_permission(Permission.USERS_READ)),
        ):
            ...
    """

    async def _check(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if not await user_has_permission(current_user, permission, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )
        return current_user

    # Set docstring for OpenAPI schema
    _check.__name__ = f"require_{permission.replace(':', '_')}"

    return _check
