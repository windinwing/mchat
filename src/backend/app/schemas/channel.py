"""Channel management Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ChannelCreate(BaseModel):
    """Create a new channel."""
    name: str = Field(..., min_length=1, max_length=100)
    channel_type: str = Field(
        ..., pattern=r"^(web_widget|wechat|dingtalk|whatsapp|telegram|slack|line|custom)$"
    )
    config: dict | None = None
    enabled: bool = False


class ChannelUpdate(BaseModel):
    """Update an existing channel."""
    name: str | None = Field(None, min_length=1, max_length=100)
    config: dict | None = None
    enabled: bool | None = None


class ChannelResponse(BaseModel):
    """Channel response."""
    id: str
    user_id: str
    name: str
    channel_type: str
    config: dict | None = None
    enabled: bool
    is_connected: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChannelTestRequest(BaseModel):
    """Test a channel connection."""
    channel_type: str
    config: dict


class ChannelWorkflowBindingItem(BaseModel):
    workflow_id: str = Field(..., min_length=1, max_length=36)
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=10000)
    match_type: str = Field(default="all")
    match_expr: str | None = None

    @field_validator("match_type")
    @classmethod
    def validate_match_type(cls, value: str) -> str:
        val = value.strip().lower()
        if val not in {"all", "contains", "regex"}:
            raise ValueError("match_type must be all, contains or regex")
        return val


class ChannelWorkflowBindingUpdate(BaseModel):
    bindings: list[ChannelWorkflowBindingItem]


class ChannelWorkflowBindingResponse(BaseModel):
    id: str
    channel_id: str
    workflow_id: str
    workflow_name: str
    enabled: bool
    priority: int
    match_type: str
    match_expr: str | None = None
    created_at: datetime
    updated_at: datetime


class ChannelWorkflowPreviewRequest(BaseModel):
    content: str = Field(default="")
    event_type: str = Field(default="message")
    dispatch_mode: str | None = None
    bindings: list[ChannelWorkflowBindingItem] | None = None

    @field_validator("dispatch_mode")
    @classmethod
    def validate_dispatch_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        val = value.strip().lower()
        if val not in {"all", "first_match"}:
            raise ValueError("dispatch_mode must be all or first_match")
        return val


class ChannelWorkflowPreviewItem(BaseModel):
    workflow_id: str
    workflow_name: str
    priority: int
    match_type: str
    match_expr: str | None = None
    matched: bool
    selected: bool
    reason_code: str
    reason_detail: str | None = None
    error: str | None = None
    matched_text: str | None = None
    match_start: int | None = None
    match_end: int | None = None


class ChannelWorkflowPreviewResponse(BaseModel):
    event_type: str
    dispatch_mode: str
    matched_workflow_ids: list[str]
    evaluations: list[ChannelWorkflowPreviewItem]


class ChannelWorkflowBindingBundle(BaseModel):
    dispatch_mode: str = Field(default="all")
    bindings: list[ChannelWorkflowBindingItem] = Field(default_factory=list)

    @field_validator("dispatch_mode")
    @classmethod
    def validate_dispatch_mode_required(cls, value: str) -> str:
        val = value.strip().lower()
        if val not in {"all", "first_match"}:
            raise ValueError("dispatch_mode must be all or first_match")
        return val


class ChannelWorkflowTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    dispatch_mode: str = Field(default="all")
    bindings: list[ChannelWorkflowBindingItem] = Field(default_factory=list)

    @field_validator("dispatch_mode")
    @classmethod
    def validate_template_dispatch_mode(cls, value: str) -> str:
        val = value.strip().lower()
        if val not in {"all", "first_match"}:
            raise ValueError("dispatch_mode must be all or first_match")
        return val


class ChannelWorkflowTemplateResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    dispatch_mode: str
    bindings: list[ChannelWorkflowBindingItem]
    usage_count: int = 0
    created_at: datetime
    updated_at: datetime


class ChannelWorkflowStatsItem(BaseModel):
    workflow_id: str
    workflow_name: str
    total_runs: int
    success_runs: int
    failed_runs: int
    last_run_at: datetime | None = None


class ChannelWorkflowStatsResponse(BaseModel):
    channel_id: str
    days: int
    items: list[ChannelWorkflowStatsItem]
