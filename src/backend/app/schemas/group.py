"""Group collaboration schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class GroupMemberResponse(BaseModel):
    id: str
    user_id: str
    username: str | None = None
    display_name: str | None = None
    user_role: str | None = None
    role: str
    created_at: datetime


class GroupResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    owner_user_id: str
    default_skill_ids: list[str] | None = None
    ai_config_id: str | None = None
    devbridge_project_allowlists: dict[str, list[str]] | None = None
    created_at: datetime
    updated_at: datetime
    current_user_role: str | None = None
    member_count: int = 0
    members: list[GroupMemberResponse] | None = None


class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    default_skill_ids: list[str] | None = None
    ai_config_id: str | None = None
    devbridge_project_allowlists: dict[str, list[str]] | None = None


class GroupUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    default_skill_ids: list[str] | None = None
    ai_config_id: str | None = None
    devbridge_project_allowlists: dict[str, list[str]] | None = None


class GroupMemberUpsertRequest(BaseModel):
    user_id: str
    role: str = Field("member", pattern=r"^(owner|editor|member)$")


class GroupChatResumeRequest(BaseModel):
    title: str | None = Field(None, max_length=200)
    force_new: bool = False


class GroupMemoryResponse(BaseModel):
    id: str
    group_id: str
    memory_type: str
    title: str
    content: str
    tags: list[str] | None = None
    topic: str | None = None
    status: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class GroupMemoryRevisionResponse(BaseModel):
    id: str
    entry_id: str
    version: int
    title: str
    content: str
    tags: list[str] | None = None
    topic: str | None = None
    status: str
    edited_by: str
    created_at: datetime


class GroupMemoryCreateRequest(BaseModel):
    memory_type: str = Field("prompt", pattern=r"^(prompt|playbook|faq|decision|example)$")
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=20000)
    tags: list[str] | None = None
    topic: str | None = Field(None, max_length=100)
    status: str = Field("draft", pattern=r"^(draft|verified|archived)$")


class GroupMemoryUpdateRequest(BaseModel):
    memory_type: str | None = Field(None, pattern=r"^(prompt|playbook|faq|decision|example)$")
    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = Field(None, min_length=1, max_length=20000)
    tags: list[str] | None = None
    topic: str | None = Field(None, max_length=100)
    status: str | None = Field(None, pattern=r"^(draft|verified|archived)$")
