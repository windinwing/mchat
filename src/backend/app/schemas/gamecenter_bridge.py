"""Schemas for GameCenter bridge (read-only MVP)."""

from datetime import datetime

from pydantic import BaseModel


class GamecenterProjectSummary(BaseModel):
    slug: str
    name: str
    path: str
    has_build: bool = False
    source_updated_at: datetime | None = None
    build_updated_at: datetime | None = None
    preview_path: str | None = None


class GamecenterProjectDetail(GamecenterProjectSummary):
    readable_roots: list[str] = []
    top_level_files: list[str] = []


class GamecenterFileEntry(BaseModel):
    path: str
    name: str
    is_dir: bool = False
    size: int = 0
    updated_at: datetime | None = None


class GamecenterFileListResponse(BaseModel):
    project: str
    path: str = ""
    items: list[GamecenterFileEntry] = []


class GamecenterFileReadResponse(BaseModel):
    project: str
    path: str
    content: str
    size: int = 0
    updated_at: datetime | None = None
