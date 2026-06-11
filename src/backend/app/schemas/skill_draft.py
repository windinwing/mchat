"""Skill draft schemas (chat → skill authoring)."""

from datetime import datetime

from pydantic import BaseModel, Field


class SkillDraftFileEntry(BaseModel):
    path: str
    content: str


class SkillDraftResponse(BaseModel):
    id: str
    conversation_id: str | None = None
    group_id: str | None = None
    name: str
    description: str | None = None
    skill_type: str = "tool"
    files: list[SkillDraftFileEntry] = Field(default_factory=list)
    status: str = "draft"
    created_at: datetime
    updated_at: datetime


class SkillDraftFromChatRequest(BaseModel):
    conversation_id: str
    hint: str | None = Field(None, max_length=2000)


class SkillDraftUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    skill_type: str | None = Field(None, pattern=r"^(tool|function|webhook)$")
    files: list[SkillDraftFileEntry] | None = None


class SkillDraftCommitRequest(BaseModel):
    customer_id: str | None = None
    bind_channel: bool = True
    group_id: str | None = None


class SkillDraftListResponse(BaseModel):
    items: list[SkillDraftResponse]
    total: int
