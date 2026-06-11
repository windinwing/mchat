"""Generic development bridge schemas."""

from pydantic import BaseModel


class DevBridgeProviderResponse(BaseModel):
    key: str
    title: str
    enabled: bool = False
    capabilities: list[str] = []


class DevBridgePatchRequest(BaseModel):
    path: str
    content: str
    summary: str | None = None


class DevBridgeChangeSummary(BaseModel):
    id: str
    provider: str
    project: str
    path: str
    summary: str | None = None
    status: str
    actor_user_id: str
    created_at: str
    reverted_at: str | None = None


class DevBridgeChangeDetail(DevBridgeChangeSummary):
    before_sha256: str
    after_sha256: str
    before_size: int
    after_size: int


class DevBridgeBuildRequest(BaseModel):
    summary: str | None = None


class DevBridgePublishRequest(BaseModel):
    build_id: str
    summary: str | None = None


class DevBridgeRollbackRequest(BaseModel):
    release_id: str


class DevBridgeBuildResult(BaseModel):
    id: str
    provider: str
    project: str
    status: str
    command: str
    build_output_dir: str | None = None
    snapshot_dir: str | None = None
    summary: str | None = None
    actor_user_id: str
    created_at: str
