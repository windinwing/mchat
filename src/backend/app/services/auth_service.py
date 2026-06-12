"""Auth service - business logic for authentication."""

import re
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse, UserResponse


_UNSET = object()
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_EXTERNAL_PROVIDER_9235 = "patent9235"


class AuthService:
    """Handles authentication business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _find_user_for_login(self, username: str) -> User | None:
        uname = (username or "").strip()
        if not uname:
            return None
        result = await self.db.execute(select(User).where(User.username == uname))
        user = result.scalar_one_or_none()
        if user is not None:
            return user
        if _PHONE_RE.match(uname):
            result = await self.db.execute(select(User).where(User.phone == uname))
            user = result.scalar_one_or_none()
            if user is not None:
                return user
            result = await self.db.execute(
                select(User).where(User.username == self._phone_username(uname))
            )
            return result.scalar_one_or_none()
        return None

    async def login(self, username: str, password: str) -> TokenResponse:
        """Authenticate user and return JWT token."""
        user = await self._find_user_for_login(username)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        if not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        access_token = create_access_token(
            data={"sub": user.id, "username": user.username, "role": user.role}
        )

        return TokenResponse(
            access_token=access_token,
            user=UserResponse.model_validate(user),
        )

    async def register(
        self,
        username: str,
        password: str,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> TokenResponse:
        """Register a new agent user."""
        # Check if username exists
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )

        now = datetime.now(timezone.utc)
        user = User(
            username=username,
            password_hash=get_password_hash(password),
            role="agent",
            display_name=display_name or username,
            avatar_url=avatar_url,
            password_set_at=now,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        access_token = create_access_token(
            data={"sub": user.id, "username": user.username, "role": user.role}
        )

        return TokenResponse(
            access_token=access_token,
            user=UserResponse.model_validate(user),
        )

    async def signup(
        self,
        username: str,
        password: str,
        email: str | None = None,
        display_name: str | None = None,
    ) -> TokenResponse:
        """Register a new public user with role='user'."""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )
        if email:
            result = await self.db.execute(
                select(User).where(User.email == email)
            )
            if result.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                )

        now = datetime.now(timezone.utc)
        user = User(
            username=username,
            email=email,
            password_hash=get_password_hash(password),
            role="user",
            display_name=display_name or username,
            account_status="active",
            password_set_at=now,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        access_token = create_access_token(
            data={"sub": user.id, "username": user.username, "role": user.role}
        )
        return TokenResponse(
            access_token=access_token,
            user=UserResponse.model_validate(user),
        )

    async def create_default_admin(
        self, username: str, password: str
    ) -> User | None:
        """Create default admin user if not exists."""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        if result.scalar_one_or_none() is not None:
            return None

        now = datetime.now(timezone.utc)
        user = User(
            username=username,
            password_hash=get_password_hash(password),
            role="admin",
            display_name="Admin",
            password_set_at=now,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def change_password(
        self,
        user: User,
        current_password: str | None,
        new_password: str,
    ) -> None:
        """Set or change password for the authenticated user."""
        if user.external_provider:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password is managed by your external account provider",
            )
        now = datetime.now(timezone.utc)
        if user.password_set_at is None:
            user.password_hash = get_password_hash(new_password)
            user.password_set_at = now
        else:
            if not current_password or not verify_password(
                current_password, user.password_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is incorrect",
                )
            user.password_hash = get_password_hash(new_password)
            user.password_set_at = now
        await self.db.flush()

    async def update_profile(
        self,
        user: User,
        *,
        display_name: str | None | object = _UNSET,
        avatar_url: str | None | object = _UNSET,
    ) -> User:
        """Update current user profile fields."""
        if display_name is not _UNSET:
            normalized = (display_name or "").strip()
            user.display_name = normalized or user.username
        if avatar_url is not _UNSET:
            normalized_url = (avatar_url or "").strip()
            user.avatar_url = normalized_url or None
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def list_users(self) -> list[User]:
        """List all users (admin)."""
        result = await self.db.execute(
            select(User).order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_user(
        self,
        username: str,
        password: str,
        role: str = "agent",
        display_name: str | None = None,
        skill_ids: list | None = None,
    ) -> User:
        """Create a user (admin)."""
        if role not in ("admin", "agent", "user"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role",
            )
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )
        user = User(
            username=username,
            password_hash=get_password_hash(password),
            role=role,
            display_name=display_name or username,
            skill_ids=skill_ids,
            password_set_at=datetime.now(timezone.utc),
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update_user(
        self,
        user_id: str,
        *,
        role: str | None = None,
        display_name: str | None = None,
        password: str | None = None,
        skill_ids: list | None = None,
        set_skill_ids: bool = False,
        workspace_container_allowed: bool | None | object = None,
        set_workspace_container_allowed: bool = False,
    ) -> User:
        """Update user fields (admin)."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        if role is not None:
            if role not in ("admin", "agent", "user"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid role",
                )
            user.role = role
        if display_name is not None:
            user.display_name = display_name
        if password is not None:
            user.password_hash = get_password_hash(password)
            user.password_set_at = datetime.now(timezone.utc)
        if set_skill_ids:
            user.skill_ids = skill_ids  # type: ignore[assignment]
        if set_workspace_container_allowed:
            user.workspace_container_allowed = workspace_container_allowed  # type: ignore[assignment]
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def delete_user(self, user_id: str, *, actor_id: str) -> None:
        """Delete a user (admin). Cannot delete self."""
        if user_id == actor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account",
            )
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        await self.db.delete(user)
        await self.db.flush()

    def _token_for_user(self, user: User) -> TokenResponse:
        access_token = create_access_token(
            data={"sub": user.id, "username": user.username, "role": user.role}
        )
        return TokenResponse(
            access_token=access_token,
            user=UserResponse.model_validate(user),
        )

    @staticmethod
    def _random_password_hash() -> str:
        return get_password_hash(secrets.token_urlsafe(32))

    @staticmethod
    def _phone_username(phone: str) -> str:
        return f"u{phone}"

    @staticmethod
    def _external_username(account: str) -> str:
        if _PHONE_RE.match(account):
            return f"u{account}"
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", account).strip("_") or "user"
        return f"e{safe[:90]}"

    async def signup_by_phone(self, phone: str) -> TokenResponse:
        """Register or sign in with a verified phone number (portal/Core signup)."""
        phone = phone.strip()
        result = await self.db.execute(select(User).where(User.phone == phone))
        user = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if user is not None:
            user.phone_verified_at = now
            await self.db.flush()
            await self.db.refresh(user)
            return self._token_for_user(user)

        username = self._phone_username(phone)
        result = await self.db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone already linked to another account",
            )

        user = User(
            username=username,
            password_hash=self._random_password_hash(),
            role="user",
            display_name=phone,
            phone=phone,
            phone_verified_at=now,
            account_status="active",
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return self._token_for_user(user)

    async def login_by_phone(self, phone: str) -> TokenResponse:
        """Sign in with a verified phone number (portal users)."""
        phone = phone.strip()
        result = await self.db.execute(select(User).where(User.phone == phone))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Phone not registered",
            )
        if user.account_status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account suspended",
            )
        user.phone_verified_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(user)
        return self._token_for_user(user)

    async def login_or_link_9235(self, *, account: str) -> TokenResponse:
        """Sign in via 9235.net SSO; create or link a portal user."""
        account = (account or "").strip()
        if account.startswith("+86") and len(account) > 3:
            account = account[3:]
        if not account:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid SSO account",
            )

        result = await self.db.execute(
            select(User).where(
                User.external_provider == _EXTERNAL_PROVIDER_9235,
                User.external_id == account,
            )
        )
        user = result.scalar_one_or_none()

        if user is None and _PHONE_RE.match(account):
            result = await self.db.execute(select(User).where(User.phone == account))
            user = result.scalar_one_or_none()
            if user is not None:
                user.external_provider = _EXTERNAL_PROVIDER_9235
                user.external_id = account
                if not user.phone_verified_at:
                    user.phone_verified_at = datetime.now(timezone.utc)

        if user is None:
            username = self._external_username(account)
            result = await self.db.execute(select(User).where(User.username == username))
            if result.scalar_one_or_none() is not None:
                username = f"{username}_{secrets.token_hex(4)}"
            user = User(
                username=username,
                password_hash=self._random_password_hash(),
                role="user",
                display_name=account,
                phone=account if _PHONE_RE.match(account) else None,
                phone_verified_at=datetime.now(timezone.utc) if _PHONE_RE.match(account) else None,
                external_provider=_EXTERNAL_PROVIDER_9235,
                external_id=account,
                account_status="active",
            )
            self.db.add(user)
        else:
            if user.account_status != "active":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account suspended",
                )

        await self.db.flush()
        await self.db.refresh(user)
        return self._token_for_user(user)
