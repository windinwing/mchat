"""Workflow schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    enabled: bool = True


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    enabled: bool | None = None
    graph_json: dict | None = None


class WorkflowGraphNode(BaseModel):
    id: str = Field(..., min_length=1, max_length=80)
    type: str = Field(..., min_length=1, max_length=40)
    name: str | None = None
    position: dict | None = None
    config: dict | None = None
    parentId: str | None = None


class WorkflowGraphEdge(BaseModel):
    id: str = Field(..., min_length=1, max_length=80)
    source: str = Field(..., min_length=1, max_length=80)
    target: str = Field(..., min_length=1, max_length=80)
    source_handle: str | None = None
    target_handle: str | None = None
    condition: str | None = None  # true, false, default


class WorkflowGraph(BaseModel):
    version: int = Field(default=1, ge=1, le=99)
    nodes: list[WorkflowGraphNode] = Field(default_factory=list)
    edges: list[WorkflowGraphEdge] = Field(default_factory=list)
    viewport: dict | None = None

    @field_validator("nodes")
    @classmethod
    def validate_nodes_not_empty_ids(cls, value: list[WorkflowGraphNode]) -> list[WorkflowGraphNode]:
        ids = [n.id for n in value]
        if len(ids) != len(set(ids)):
            raise ValueError("graph node ids must be unique")
        return value


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    enabled: bool
    graph_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowStepInput(BaseModel):
    step_key: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    order_index: int = Field(default=0, ge=0, le=9999)
    skill_id: str = Field(..., min_length=1, max_length=36)
    payload_template: dict | None = None
    on_error: str = Field(default="stop")
    enabled: bool = True

    @field_validator("on_error")
    @classmethod
    def validate_on_error(cls, value: str) -> str:
        val = value.strip().lower()
        if val not in {"stop", "continue"}:
            raise ValueError("on_error must be stop or continue")
        return val


class WorkflowStepResponse(BaseModel):
    id: str
    step_key: str
    name: str
    order_index: int
    skill_id: str
    skill_name: str
    payload_template: dict | None = None
    on_error: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class WorkflowStepsPutRequest(BaseModel):
    steps: list[WorkflowStepInput]


class WorkflowRunOnceRequest(BaseModel):
    payload: dict | None = None


class WorkflowRunRenameRequest(BaseModel):
    run_label: str = Field(..., min_length=1, max_length=120)


class WorkflowRunResumeRequest(BaseModel):
    payload: dict | None = None


class WorkflowStepRunResponse(BaseModel):
    id: str
    step_id: str
    step_key: str
    step_name: str
    skill_id: str
    skill_name: str
    status: str
    payload: dict | None = None
    result: dict | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    display_name: str = ""
    trigger_type: str
    status: str
    input_payload: dict | None = None
    output_payload: dict | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None


class WorkflowRunDetailResponse(WorkflowRunResponse):
    step_runs: list[WorkflowStepRunResponse]
    node_runs: list[dict] | None = None
    pending_approvals: list["WorkflowApprovalResponse"] = Field(default_factory=list)
    can_resume: bool = False


class WorkflowApprovalResponse(BaseModel):
    id: str
    workflow_run_id: str
    workflow_id: str
    workflow_name: str
    node_id: str
    node_name: str | None = None
    status: str
    request_payload: dict | None = None
    decision_payload: dict | None = None
    comment: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    approved_by: str | None = None


class WorkflowApprovalDecisionRequest(BaseModel):
    comment: str | None = None
    decision_payload: dict | None = None
    auto_resume: bool = True


class WorkflowTemplateSummary(BaseModel):
    id: str
    name: str
    description: str
    category: str = "general"
    locale: str | None = None
    node_count: int = 0
    builtin: bool = True
    visibility: str = "system"
    author_id: str | None = None
    author_name: str | None = None
    use_count: int = 0
    is_mine: bool = False


class WorkflowMarketplaceResponse(BaseModel):
    system: list[WorkflowTemplateSummary] = []
    community: list[WorkflowTemplateSummary] = []
    mine: list[WorkflowTemplateSummary] = []


class WorkflowTemplateVisibilityUpdate(BaseModel):
    visibility: str = Field(
        ...,
        pattern=r"^(private|shared|system)$",
        description="private=only owner; shared=all users; system=featured (admin)",
    )


class WorkflowTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    category: str = Field(default="custom", max_length=40)
    locale: str | None = Field(default=None, max_length=8)


class WorkflowSaveAsTemplateRequest(WorkflowTemplateCreate):
    """Save an existing workflow graph as a reusable template."""

    visibility: str = Field(
        default="private",
        pattern=r"^(private|shared|system)$",
    )


class WorkflowCreateFromTemplateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    enabled: bool = True


class WorkflowPatentShowcaseConfig(BaseModel):
    """Configurable patent workflow demo — skills live outside mchat repo."""

    enabled: bool = True
    search_skill: str = "patent-search"
    report_skill: str = "patent-report"
    skills_dir: str = ""
    extra_skills_dirs: list[str] = Field(default_factory=list)
    patent_skills_source: str = ""
    installed: dict[str, bool] = Field(default_factory=dict)
    on_disk: dict[str, bool] = Field(default_factory=dict)
    ready: bool = False

