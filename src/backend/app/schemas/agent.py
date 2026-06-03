"""Agent configuration Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_AUTO_REPLY_CHANNELS = {"widget", "wechat", "admin"}


class AutoReplyAsset(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)
    name: str | None = Field(None, max_length=255)
    title: str | None = Field(None, max_length=255)
    mime: str | None = Field(None, max_length=255)
    type: str | None = Field(None, max_length=50)


class AutoReplyRule(BaseModel):
    id: str | None = Field(None, max_length=64)
    name: str = Field(..., min_length=1, max_length=120)
    enabled: bool = True
    trigger_text: str = Field(..., min_length=1, max_length=1000)
    keywords: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    reply_text: str | None = Field(None, max_length=2000)
    threshold: float = Field(0.78, ge=0.0, le=1.0)
    asset: AutoReplyAsset

    @field_validator("channels", mode="before")
    @classmethod
    def normalize_channels(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            text = str(item or "").strip().lower()
            if text and text in _AUTO_REPLY_CHANNELS and text not in out:
                out.append(text)
        return out


class UploadedAssetResponse(BaseModel):
    url: str
    name: str
    mime: str
    size: int
    type: str


class AIConfigCreate(BaseModel):
    """Request body for creating an AI config."""
    name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(..., min_length=1, max_length=50)
    model: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field("", max_length=500)
    api_base: str | None = Field(None, max_length=500)
    system_prompt: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1)
    is_default: bool = False


class AIConfigUpdate(BaseModel):
    """Request body for updating an AI config."""
    name: str | None = Field(None, min_length=1, max_length=100)
    provider: str | None = Field(None, max_length=50)
    model: str | None = Field(None, min_length=1, max_length=100)
    api_key: str | None = Field(None, min_length=1, max_length=500)
    api_base: str | None = Field(None, max_length=500)
    system_prompt: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1)
    is_default: bool | None = None


class AIConfigResponse(BaseModel):
    """AI config response schema."""
    id: str
    user_id: str
    name: str
    provider: str
    model: str
    api_base: str | None = None
    system_prompt: str | None = None
    temperature: float
    max_tokens: int
    is_default: bool
    created_at: datetime
    updated_at: datetime
    api_key: str  # Return full key for admin panel display

    model_config = {"from_attributes": True}


class CustomerConfigCreate(BaseModel):
    """Request body for creating a customer config."""
    name: str = Field(..., min_length=1, max_length=200)
    short_code: str | None = Field(
        None, max_length=32,
        description="Url-safe short alias, e.g. 'gdz' → /go/gdz"
    )

    @field_validator("short_code", mode="before")
    @classmethod
    def normalize_short_code(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip().lower()
        if not cleaned or cleaned in ("none", "null"):
            return None
        if not cleaned[0].isalnum():
            raise ValueError("Must start with a letter or digit")
        return cleaned
    ai_config_id: str | None = None
    skill_ids: list[str] = Field(default_factory=list)
    knowledge_base_ids: list[str] = Field(default_factory=list)
    auto_reply_rules: list[AutoReplyRule] = Field(default_factory=list)
    channel_prompt: str | None = Field(
        None,
        description="Channel-only system instructions (skills, routing); appended after AI config prompt",
    )
    welcome_message: str | None = None
    offline_message: str | None = None
    theme: dict | None = None
    domains: str | None = None
    position: str = Field("right", pattern=r"^(left|right)$")
    pre_chat_fields: list[dict] | None = Field(
        None,
        description="Optional pre-chat form fields: [{key, label, required?, type?}]",
    )
    enabled: bool = True
    widget_session_ttl_hours: int = Field(
        24, ge=0, le=24 * 365, description="0 = never expire by time"
    )
    workspace_mode: str | None = Field(
        None,
        description="Execution override: local | container; null = auto from subscription plan",
    )

    @field_validator("workspace_mode", mode="before")
    @classmethod
    def normalize_workspace_mode(cls, v: str | None) -> str | None:
        if v is None or str(v).strip() == "":
            return None
        mode = str(v).strip().lower()
        if mode not in ("local", "container"):
            raise ValueError("workspace_mode must be local or container")
        return mode


class ModelCatalogRequest(BaseModel):
    """Probe provider API to list models."""
    provider: str = Field(..., min_length=1, max_length=50)
    api_key: str = Field("", max_length=500)
    api_base: str | None = Field(None, max_length=500)
    config_id: str | None = None


class ModelCatalogResponse(BaseModel):
    models: list[str]


class ConnectionTestRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=50)
    api_key: str = Field("", max_length=500)
    api_base: str | None = Field(None, max_length=500)
    model: str | None = Field(None, max_length=100)
    config_id: str | None = None


class ConnectionTestResponse(BaseModel):
    ok: bool
    message: str


class CustomerConfigResponse(BaseModel):
    """Customer config response schema."""
    id: str
    name: str
    short_code: str | None = None
    user_id: str
    ai_config_id: str | None = None
    skill_ids: list[str] | None = None
    knowledge_base_ids: list[str] | None = None
    auto_reply_rules: list[AutoReplyRule] | None = None
    channel_prompt: str | None = None
    welcome_message: str | None = None
    offline_message: str | None = None
    theme: dict | None = None
    domains: str | None = None
    position: str
    pre_chat_fields: list[dict] | None = None
    enabled: bool
    widget_session_ttl_hours: int = 24
    workspace_mode: str | None = None
    workspace_container_allowed: bool | None = Field(
        None,
        description="Owner account container policy (read-only)",
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
