"""First-run / setup status schemas."""

from pydantic import BaseModel, Field


class SetupStatusResponse(BaseModel):
    """Whether the tenant can chat yet (AI + optional assistant)."""

    ai_ready: bool = Field(description="At least one AI config with a usable API key")
    has_assistant: bool = Field(
        description="At least one enabled customer agent / channel assistant"
    )
    ai_config_count: int = 0
    env_key_providers: list[str] = Field(
        default_factory=list,
        description="Providers with keys in server .env (still need a model entry in UI)",
    )
