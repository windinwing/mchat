"""Portal schemas — user-facing channel rental API."""

from datetime import datetime

from pydantic import BaseModel, Field


class ChannelTemplateResponse(BaseModel):
    """Published channel template shown in the marketplace."""

    id: str
    name: str
    description: str | None = None
    category: str
    icon: str | None = None
    price_monthly_cents: int = 0
    price_yearly_cents: int = 0
    trial_days: int = 14
    max_publishing_accounts: int = 0
    integration_schema: list | None = None
    default_theme: dict | None = None
    default_welcome_message: str | None = None
    default_offline_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RentChannelRequest(BaseModel):
    """Request to provision a channel from a template."""

    template_id: str = Field(..., min_length=1)
    name: str | None = Field(None, max_length=200)


class SkillIntegrationFieldSchema(BaseModel):
    key: str
    label: str
    secret: bool = True
    placeholder: str | None = None
    help: str | None = None


class SkillIntegrationBlockSchema(BaseModel):
    skill: str
    fields: list[SkillIntegrationFieldSchema]
    allow_channel_override: bool = True
    source: str | None = None  # skill | template


class ChannelIntegrationsResponse(BaseModel):
    """Skills on this channel that may need per-channel API tokens."""

    integrations: list[SkillIntegrationBlockSchema]
    skill_bindings: dict | None = None


class PortalAiConfigOption(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    is_default: bool = False
    has_api_key: bool = False


class MyChannelResponse(BaseModel):
    """User's channel summary with usage stats."""

    id: str
    name: str
    short_code: str | None = None
    channel_category: str
    template_id: str | None = None
    ai_config_id: str | None = None
    ai_override: bool = False
    ai_provider: str | None = None
    ai_model: str | None = None
    template_default_ai_config_id: str | None = None
    plan: str
    trial_ends_at: datetime | None = None
    subscription_ends_at: datetime | None = None
    subscription_active: bool = True
    active_order_id: str | None = None
    skill_bindings: dict | None = None
    enabled: bool
    welcome_message: str | None = None
    offline_message: str | None = None
    theme: dict | None = None
    # Usage stats
    usage_messages_month: int = 0
    usage_tokens_month: int = 0
    usage_messages_limit: int = 1000
    usage_tokens_limit: int = 100000
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MyChannelUpdate(BaseModel):
    """User-facing channel settings update."""

    name: str | None = Field(None, max_length=200)
    welcome_message: str | None = None
    offline_message: str | None = None
    theme: dict | None = None
    enabled: bool | None = None
    skill_bindings: dict | None = None
    ai_config_id: str | None = None
    ai_override: bool | None = None


class PortalOrderResponse(BaseModel):
    """User-visible order record."""

    id: str
    order_no: str
    template_id: str
    channel_id: str | None = None
    channel_name: str | None = None
    billing_period: str
    amount_cents: int
    subject: str
    status: str
    payment_method: str | None = None
    provider_trade_no: str | None = None
    subscription_ends_at: datetime | None = None
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PortalOrderDetailResponse(PortalOrderResponse):
    """Order detail with template name for UI / invoice."""

    template_name: str | None = None
    is_renewal: bool = False


class AdminOrderResponse(PortalOrderResponse):
    """Admin view of portal order with buyer info."""

    user_username: str | None = None
    user_phone: str | None = None
    user_email: str | None = None


class AdminRevenueStats(BaseModel):
    paid_order_count: int = 0
    total_revenue_cents: int = 0
    month_revenue_cents: int = 0
    pending_order_count: int = 0


class PortalAiConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(..., min_length=1, max_length=50)
    model: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field("", max_length=500)
    api_base: str | None = Field(None, max_length=500)
    system_prompt: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1)


class PortalAiConfigUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    provider: str | None = Field(None, max_length=50)
    model: str | None = Field(None, max_length=100)
    api_key: str | None = Field(None, max_length=500)
    api_base: str | None = Field(None, max_length=500)
    system_prompt: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1)


class PortalInvoiceResponse(BaseModel):
    """Printable invoice payload (client renders)."""

    order_no: str
    status: str
    subject: str
    template_name: str | None = None
    channel_name: str | None = None
    billing_period: str
    amount_cents: int
    amount_yuan: str
    payment_method: str | None = None
    provider_trade_no: str | None = None
    paid_at: datetime | None = None
    subscription_ends_at: datetime | None = None
    created_at: datetime
    company_name: str
    company_tax_id: str | None = None
    support_email: str | None = None
    buyer_email: str | None = None
    buyer_phone: str | None = None


class EmbedCodeResponse(BaseModel):
    """Widget embed code for a channel."""

    agent_id: str
    embed_script: str
    widget_url: str


class PortalDashboardStats(BaseModel):
    """Dashboard stats for the portal."""

    total_channels: int = 0
    active_channels: int = 0
    total_conversations: int = 0
    messages_today: int = 0
    # Aggregated usage across all channels
    total_messages_month: int = 0
    total_tokens_month: int = 0
    plan: str | None = None
    trial_ends_at: datetime | None = None


class StudioMemoryResponse(BaseModel):
    """Markdown memory workspace summary for a channel."""

    memory_md: str = ""
    daily_dates: list[str] = Field(default_factory=list)


class StudioMemoryUpdate(BaseModel):
    """User-edited long-term MEMORY.md content."""

    content: str = ""


class StudioDailyMemoryResponse(BaseModel):
    """Single daily memory log file."""

    date: str
    content: str = ""


class ResumeChannelChatRequest(BaseModel):
    """Resume portal studio chat for a channel."""

    title: str | None = Field(None, max_length=200)
    force_new: bool = Field(
        False,
        description="Close the current active channel chat and start a new conversation",
    )
