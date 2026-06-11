"""Chat-related Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    """Request body for sending a chat message."""
    conversation_id: str | None = Field(None, description="Existing conversation ID")
    content: str = Field(..., min_length=1, max_length=10000)
    role: str = Field("user", pattern=r"^(user|assistant|system)$")
    extra_data: dict | None = Field(None, description="Optional message metadata such as attachments or outbound assets")


class MessageResponse(BaseModel):
    """Message response schema."""
    id: str
    conversation_id: str
    role: str
    content: str
    extra_data: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelCapabilitiesResponse(BaseModel):
    """Chat UI hints derived from the bound LLM provider/model."""
    supports_attachments: bool = True
    supports_vision: bool = False


class ConversationResponse(BaseModel):
    """Conversation response schema."""
    id: str
    title: str | None = None
    status: str
    conversation_type: str = "chat"
    user_id: str | None = None
    username: str | None = None
    first_user_message_preview: str | None = None
    visitor_id: str | None = None
    client_ip: str | None = None
    contact_info: str | None = None
    customer_id: str | None = None
    scope_type: str = "personal"
    scope_id: str | None = None
    scope_name: str | None = None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime
    user_message_count: int = 0
    ai_message_count: int = 0
    total_message_count: int = 0
    messages: list[MessageResponse] | None = None
    ai_capabilities: ModelCapabilitiesResponse | None = None

    model_config = {"from_attributes": True}


class ConversationList(BaseModel):
    """Paginated conversation list."""
    items: list[ConversationResponse]
    total: int


class ConversationStatsResponse(BaseModel):
    """Conversation aggregate stats."""
    total: int
    active: int
    closed: int


class InitConversationRequest(BaseModel):
    """Initialize a visitor conversation."""
    visitor_id: str | None = Field(None, max_length=100)
    title: str | None = Field(None, max_length=200)
    ai_config_id: str | None = None
    contact_info: str | None = None


class CreateConversationRequest(BaseModel):
    """Request body for creating a conversation (admin or portal user)."""
    title: str | None = Field(None, max_length=200)
    ai_config_id: str | None = None
    visitor_id: str | None = Field(None, max_length=100)
    customer_id: str | None = Field(
        None,
        description="Channel (CustomerConfig) id — binds AI config, skills, and knowledge",
    )
    scope_type: str = Field("personal", pattern=r"^(personal|group|channel_public)$")
    scope_id: str | None = None


class ResumeConversationRequest(BaseModel):
    """Resume the latest active thread for a channel, or start a new one."""
    customer_id: str = Field(..., min_length=1, description="Channel (CustomerConfig) id")
    title: str | None = Field(None, max_length=200)
    force_new: bool = False
    scope_type: str = Field("personal", pattern=r"^(personal|group|channel_public)$")
    scope_id: str | None = None
