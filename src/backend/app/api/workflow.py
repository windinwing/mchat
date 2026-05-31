"""Workflow API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import Permission, require_permission
from app.models.user import User
from app.schemas.workflow import (
    WorkflowApprovalDecisionRequest,
    WorkflowApprovalResponse,
    WorkflowCreate,
    WorkflowCreateFromTemplateRequest,
    WorkflowResponse,
    WorkflowRunDetailResponse,
    WorkflowRunResumeRequest,
    WorkflowRunOnceRequest,
    WorkflowRunResponse,
    WorkflowStepResponse,
    WorkflowStepsPutRequest,
    WorkflowTemplateSummary,
    WorkflowUpdate,
)
from app.services.workflow_service import WorkflowService

router = APIRouter()


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).list_workflows(user_id=admin.id)


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    request: WorkflowCreate,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).create_workflow(user_id=admin.id, data=request)


@router.get("/templates", response_model=list[WorkflowTemplateSummary])
async def list_workflow_templates(
    locale: str | None = None,
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
):
    return WorkflowService.list_templates(locale=locale)


@router.post("/from-template/{template_id}", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow_from_template(
    template_id: str,
    request: WorkflowCreateFromTemplateRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).create_from_template(
        user_id=admin.id,
        template_id=template_id,
        name=request.name,
        description=request.description,
        enabled=request.enabled,
    )


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    request: WorkflowUpdate,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).update_workflow(
        workflow_id=workflow_id, user_id=admin.id, data=request
    )


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: str,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    await WorkflowService(db).delete_workflow(workflow_id=workflow_id, user_id=admin.id)
    return None


@router.get("/{workflow_id}/steps", response_model=list[WorkflowStepResponse])
async def list_workflow_steps(
    workflow_id: str,
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).list_steps(workflow_id=workflow_id, user_id=admin.id)


@router.put("/{workflow_id}/steps", response_model=list[WorkflowStepResponse])
async def replace_workflow_steps(
    workflow_id: str,
    request: WorkflowStepsPutRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).replace_steps(
        workflow_id=workflow_id, user_id=admin.id, steps=request.steps
    )


@router.post("/{workflow_id}/run-once", response_model=WorkflowRunDetailResponse)
async def run_workflow_once(
    workflow_id: str,
    request: WorkflowRunOnceRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).run_once(
        workflow_id=workflow_id, user_id=admin.id, input_payload=request.payload
    )


@router.get("/runs/list", response_model=list[WorkflowRunResponse])
async def list_workflow_runs(
    workflow_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).list_runs(
        user_id=admin.id, workflow_id=workflow_id, limit=limit
    )


@router.get("/runs/{run_id}", response_model=WorkflowRunDetailResponse)
async def get_workflow_run_detail(
    run_id: str,
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).get_run_detail(run_id=run_id, user_id=admin.id)


@router.post("/runs/{run_id}/resume", response_model=WorkflowRunDetailResponse)
async def resume_workflow_run(
    run_id: str,
    request: WorkflowRunResumeRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).resume_run(
        run_id=run_id,
        user_id=admin.id,
        request=request,
    )


@router.get("/approvals/pending", response_model=list[WorkflowApprovalResponse])
async def list_pending_approvals(
    workflow_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    admin: User = Depends(require_permission(Permission.SKILLS_READ)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).list_pending_approvals(
        user_id=admin.id,
        workflow_id=workflow_id,
        limit=limit,
    )


@router.post("/approvals/{approval_id}/approve", response_model=WorkflowApprovalResponse)
async def approve_workflow_task(
    approval_id: str,
    request: WorkflowApprovalDecisionRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).approve_task(
        approval_id=approval_id,
        user_id=admin.id,
        request=request,
    )


@router.post("/approvals/{approval_id}/reject", response_model=WorkflowApprovalResponse)
async def reject_workflow_task(
    approval_id: str,
    request: WorkflowApprovalDecisionRequest,
    admin: User = Depends(require_permission(Permission.SKILLS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService(db).reject_task(
        approval_id=approval_id,
        user_id=admin.id,
        request=request,
    )
