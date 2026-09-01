"""Optional signup schemas shared by Core and Cloud editions."""

from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    """Legacy username/password signup used by the portal entry point."""

    username: str = Field(
        ..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_]+$"
    )
    email: str | None = Field(None, max_length=255)
    password: str = Field(..., min_length=6, max_length=255)
    display_name: str | None = Field(None, max_length=100)


class SendSmsRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)


class PhoneSignupRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    code: str = Field(..., min_length=4, max_length=8)


class Sso9235CallbackRequest(BaseModel):
    xtk: str = Field(..., min_length=10)
    channel: str | None = None


class SsoLoginUrlResponse(BaseModel):
    url: str
