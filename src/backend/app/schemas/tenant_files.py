"""Tenant workspace file schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class TenantFileEntry(BaseModel):
    path: str
    name: str
    size: int
    is_dir: bool = False
    modified_at: datetime | None = None


class TenantFileListResponse(BaseModel):
    subdir: str
    items: list[TenantFileEntry]
    total: int


class TenantFileUploadResponse(BaseModel):
    path: str
    name: str
    size: int
    url: str


class TenantFileDeleteRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=500)
