"""Auth-related Pydantic schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class LoginRequest(BaseModel):
    """Request body for user login."""

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=255)


class RegisterRequest(BaseModel):
    """Request body for user registration (admin/agent only)."""

    username: str = Field(
        ..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_]+$"
    )
    password: str = Field(..., min_length=6, max_length=255)
    display_name: str | None = Field(None, max_length=100)
    avatar_url: str | None = Field(None, max_length=500)


class UserResponse(BaseModel):
    """User info response."""

    id: str
    username: str
    role: str
    email: str | None = None
    phone: str | None = None
    external_provider: str | None = None
    account_status: str = "active"
    avatar_url: str | None = None
    display_name: str | None = None
    skill_ids: list | None = None
    workspace_container_allowed: bool | None = None
    password_set_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_password(self) -> bool:
        return self.password_set_at is not None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def can_set_password(self) -> bool:
        return not self.external_provider


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class BootstrapResponse(BaseModel):
    """Default credentials hint for first-time setup."""

    username: str
    password: str | None = None
    show_credentials: bool = False


class ChangePasswordRequest(BaseModel):
    """Change or set password for the current user."""

    current_password: str | None = Field(
        None, min_length=1, max_length=255
    )
    new_password: str = Field(..., min_length=6, max_length=255)


class UpdateProfileRequest(BaseModel):
    """Update the current user's profile."""

    display_name: str | None = Field(None, max_length=100)
    avatar_url: str | None = Field(None, max_length=500)


class CreateUserRequest(BaseModel):
    """Admin: create a new user."""

    username: str = Field(
        ..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_]+$"
    )
    password: str = Field(..., min_length=6, max_length=255)
    role: Literal["admin", "agent", "user"] = "agent"
    display_name: str | None = Field(None, max_length=100)
    skill_ids: list | None = Field(None, description="Allowed skill IDs; null=unlimited")


class UpdateUserRequest(BaseModel):
    """Admin: update user role or display name."""

    role: Literal["admin", "agent", "user"] | None = None
    display_name: str | None = Field(None, max_length=100)
    skill_ids: list | None = Field(None, description="Allowed skill IDs; null=unlimited")
    password: str | None = Field(None, min_length=6, max_length=255)
    workspace_container_allowed: bool | None = Field(
        None,
        description="Container sidecar policy: null=auto by plan, true=allow, false=deny",
    )
