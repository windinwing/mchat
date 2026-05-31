"""Workflow orchestration service."""

from __future__ import annotations

import re
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import httpx

from app.models.skill import Skill
from app.models.setting import Setting
from app.models.workflow import (
    SkillWorkflowApproval,
    SkillWorkflow,
    SkillWorkflowRun,
    SkillWorkflowStep,
    SkillWorkflowStepRun,
)
from app.schemas.workflow import (
    WorkflowApprovalDecisionRequest,
    WorkflowApprovalResponse,
    WorkflowGraph,
    WorkflowCreate,
    WorkflowResponse,
    WorkflowRunDetailResponse,
    WorkflowRunResumeRequest,
    WorkflowRunResponse,
    WorkflowStepInput,
    WorkflowStepResponse,
    WorkflowStepRunResponse,
    WorkflowUpdate,
)
from app.data.workflow_templates import get_workflow_template, list_workflow_templates
from app.skill.executor import execute_skill

_TEMPLATE_RE = re.compile(r"\$\{([^}]+)\}")
logger = logging.getLogger(__name__)


def _ensure_graph_valid(graph_json: dict | None) -> dict | None:
    if not graph_json:
        return graph_json
    graph = WorkflowGraph.model_validate(graph_json)
    node_ids = {n.id for n in graph.nodes}
    for edge in graph.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid edge {edge.id}: unknown source/target",
            )
    starts = [n for n in graph.nodes if n.type == "start"]
    ends = [n for n in graph.nodes if n.type == "end"]
    if not starts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Graph must contain one start node",
        )
    if not ends:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Graph must contain at least one end node",
        )
    return graph.model_dump()


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _to_result_dict(result: Any) -> dict:
    if isinstance(result, dict):
        return result
    if isinstance(result, (str, int, float, bool, list)):
        return {"value": result}
    return {"value": str(result)}


def _resolve_path(path: str, context: dict[str, Any]) -> Any:
    current: Any = context
    for key in path.split("."):
        key = key.strip()
        if not key:
            continue
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _render_template(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: _render_template(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_template(v, context) for v in value]
    if not isinstance(value, str):
        return value

    match = _TEMPLATE_RE.fullmatch(value.strip())
    if match:
        return _resolve_path(match.group(1).strip(), context)

    def replace_var(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        resolved = _resolve_path(key, context)
        if resolved is None:
            return ""
        if isinstance(resolved, (dict, list)):
            return str(resolved)
        return str(resolved)

    return _TEMPLATE_RE.sub(replace_var, value)


class WorkflowService:
    """Business logic for workflow CRUD and execution."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_workflow(self, *, workflow_id: str, user_id: str) -> SkillWorkflow:
        result = await self.db.execute(
            select(SkillWorkflow)
            .where(SkillWorkflow.id == workflow_id, SkillWorkflow.user_id == user_id)
            .options(selectinload(SkillWorkflow.steps))
        )
        workflow = result.scalar_one_or_none()
        if workflow is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found"
            )
        return workflow

    async def _get_skill(self, *, skill_id: str, user_id: str) -> Skill:
        result = await self.db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.user_id == user_id)
        )
        skill = result.scalar_one_or_none()
        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Skill not found: {skill_id}",
            )
        return skill

    async def _get_skill_by_name(self, *, skill_name: str, user_id: str) -> Skill | None:
        result = await self.db.execute(
            select(Skill).where(Skill.name == skill_name, Skill.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _resolve_graph_skill_ids(self, graph_json: dict, *, user_id: str) -> dict:
        graph = dict(graph_json or {})
        nodes = list(graph.get("nodes") or [])
        resolved: list[dict[str, Any]] = []
        for node in nodes:
            item = dict(node)
            cfg = dict(item.get("config") or {})
            if item.get("type") == "skill" and not str(cfg.get("skill_id") or "").strip():
                skill_name = str(cfg.get("skill_name") or "").strip()
                if skill_name:
                    skill = await self._get_skill_by_name(skill_name=skill_name, user_id=user_id)
                    if skill is not None:
                        cfg["skill_id"] = skill.id
            item["config"] = cfg
            resolved.append(item)
        graph["nodes"] = resolved
        return graph

    async def _get_run(self, *, run_id: str, user_id: str) -> SkillWorkflowRun:
        result = await self.db.execute(
            select(SkillWorkflowRun)
            .where(SkillWorkflowRun.id == run_id, SkillWorkflowRun.user_id == user_id)
            .options(selectinload(SkillWorkflowRun.approvals))
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow run not found",
            )
        return run

    async def _workflow_name_map(self, workflow_ids: list[str]) -> dict[str, str]:
        if not workflow_ids:
            return {}
        res = await self.db.execute(
            select(SkillWorkflow).where(SkillWorkflow.id.in_(workflow_ids))  # type: ignore[arg-type]
        )
        return {w.id: w.name for w in res.scalars().all()}

    async def _alert_webhook_url(self) -> str | None:
        env_url = os.getenv("WORKFLOW_ALERT_WEBHOOK_URL", "").strip()
        if env_url:
            return env_url
        row = (
            await self.db.execute(
                select(Setting).where(Setting.key == "workflow.alert_webhook_url")
            )
        ).scalar_one_or_none()
        if row and row.value:
            return row.value.strip() or None
        return None

    async def _send_alert(
        self,
        *,
        event: str,
        workflow: SkillWorkflow,
        run: SkillWorkflowRun,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        webhook = await self._alert_webhook_url()
        if not webhook:
            return
        payload = {
            "event": event,
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
            "run_id": run.id,
            "run_status": run.status,
            "message": message,
            "trigger_type": run.trigger_type,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "extra": extra or {},
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.post(webhook, json=payload)
        except Exception as e:
            logger.warning("workflow alert webhook failed: run=%s err=%s", run.id, e)

    async def list_workflows(self, *, user_id: str) -> list[WorkflowResponse]:
        result = await self.db.execute(
            select(SkillWorkflow)
            .where(SkillWorkflow.user_id == user_id)
            .order_by(SkillWorkflow.created_at.desc())
        )
        rows = result.scalars().all()
        return [
            WorkflowResponse(
                id=row.id,
                name=row.name,
                description=row.description,
                enabled=row.enabled,
                graph_json=row.graph_json,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def create_workflow(
        self, *, user_id: str, data: WorkflowCreate
    ) -> WorkflowResponse:
        workflow = SkillWorkflow(
            user_id=user_id,
            name=data.name.strip(),
            description=(data.description or "").strip() or None,
            enabled=data.enabled,
            graph_json=None,
        )
        self.db.add(workflow)
        await self.db.flush()
        return WorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            enabled=workflow.enabled,
            graph_json=workflow.graph_json,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )

    @staticmethod
    def list_templates(*, locale: str | None = None) -> list[dict[str, Any]]:
        return list_workflow_templates(locale=locale)

    async def create_from_template(
        self,
        *,
        user_id: str,
        template_id: str,
        name: str | None = None,
        description: str | None = None,
        enabled: bool = True,
    ) -> WorkflowResponse:
        tpl = get_workflow_template(template_id)
        if tpl is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow template not found",
            )
        graph_json = await self._resolve_graph_skill_ids(
            tpl["graph_json"], user_id=user_id
        )
        graph_json = _ensure_graph_valid(graph_json)
        workflow = SkillWorkflow(
            user_id=user_id,
            name=(name or tpl["name"]).strip(),
            description=(description if description is not None else tpl.get("description")),
            enabled=enabled,
            graph_json=graph_json,
        )
        self.db.add(workflow)
        await self.db.flush()
        return WorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            enabled=workflow.enabled,
            graph_json=workflow.graph_json,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )

    async def update_workflow(
        self, *, workflow_id: str, user_id: str, data: WorkflowUpdate
    ) -> WorkflowResponse:
        workflow = await self._get_workflow(workflow_id=workflow_id, user_id=user_id)
        payload = data.model_dump(exclude_unset=True)
        if "name" in payload and payload["name"] is not None:
            workflow.name = payload["name"].strip()
        if "description" in payload:
            workflow.description = (payload["description"] or "").strip() or None
        if "enabled" in payload and payload["enabled"] is not None:
            workflow.enabled = bool(payload["enabled"])
        if "graph_json" in payload:
            graph = payload["graph_json"]
            if graph:
                graph = await self._resolve_graph_skill_ids(graph, user_id=user_id)
            workflow.graph_json = _ensure_graph_valid(graph)
        await self.db.flush()
        return WorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            enabled=workflow.enabled,
            graph_json=workflow.graph_json,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )

    async def delete_workflow(self, *, workflow_id: str, user_id: str) -> None:
        workflow = await self._get_workflow(workflow_id=workflow_id, user_id=user_id)
        await self.db.delete(workflow)
        await self.db.flush()

    async def list_steps(self, *, workflow_id: str, user_id: str) -> list[WorkflowStepResponse]:
        workflow = await self._get_workflow(workflow_id=workflow_id, user_id=user_id)
        ordered = sorted(workflow.steps, key=lambda x: (x.order_index, x.created_at))
        skill_ids = [s.skill_id for s in ordered]
        skill_map: dict[str, Skill] = {}
        if skill_ids:
            res = await self.db.execute(
                select(Skill).where(Skill.id.in_(skill_ids))  # type: ignore[arg-type]
            )
            skill_map = {s.id: s for s in res.scalars().all()}
        return [
            WorkflowStepResponse(
                id=s.id,
                step_key=s.step_key,
                name=s.name,
                order_index=s.order_index,
                skill_id=s.skill_id,
                skill_name=(skill_map.get(s.skill_id).name if skill_map.get(s.skill_id) else ""),
                payload_template=s.payload_template,
                on_error=s.on_error,
                enabled=s.enabled,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in ordered
        ]

    async def replace_steps(
        self,
        *,
        workflow_id: str,
        user_id: str,
        steps: list[WorkflowStepInput],
    ) -> list[WorkflowStepResponse]:
        workflow = await self._get_workflow(workflow_id=workflow_id, user_id=user_id)
        seen_keys: set[str] = set()
        for step in steps:
            key = step.step_key.strip()
            if key in seen_keys:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Duplicate step_key: {key}",
                )
            seen_keys.add(key)
            await self._get_skill(skill_id=step.skill_id, user_id=user_id)

        for row in list(workflow.steps):
            await self.db.delete(row)
        await self.db.flush()

        for item in sorted(steps, key=lambda x: x.order_index):
            row = SkillWorkflowStep(
                workflow_id=workflow.id,
                step_key=item.step_key.strip(),
                name=item.name.strip(),
                order_index=item.order_index,
                skill_id=item.skill_id,
                payload_template=item.payload_template,
                on_error=item.on_error,
                enabled=item.enabled,
            )
            self.db.add(row)
        await self.db.flush()
        return await self.list_steps(workflow_id=workflow.id, user_id=user_id)

    async def _execute_graph_workflow(
        self,
        *,
        workflow: SkillWorkflow,
        run: SkillWorkflowRun,
        input_payload: dict,
        resume_state: dict | None = None,
        approved_nodes: set[str] | None = None,
    ) -> tuple[str, str | None, dict]:
        graph_data = _ensure_graph_valid(workflow.graph_json)
        graph = WorkflowGraph.model_validate(graph_data or {})
        nodes = {n.id: n for n in graph.nodes}
        incoming: dict[str, list[str]] = {nid: [] for nid in nodes}
        outgoing: dict[str, list[Any]] = {nid: [] for nid in nodes}
        for edge in graph.edges:
            incoming[edge.target].append(edge.source)
            outgoing[edge.source].append(edge)

        done: set[str] = set(
            [str(x) for x in ((resume_state or {}).get("done_nodes") or []) if str(x) in nodes]
        )
        outputs: dict[str, Any] = {"input": input_payload, "nodes": {}}
        if isinstance((resume_state or {}).get("outputs"), dict):
            outputs["nodes"] = dict((resume_state or {}).get("outputs") or {})
        node_runs: list[dict[str, Any]] = list((resume_state or {}).get("node_runs") or [])
        approved_nodes = approved_nodes or set()
        ready: list[str] = []
        if resume_state and isinstance(resume_state.get("ready_nodes"), list):
            ready = [str(x) for x in (resume_state.get("ready_nodes") or []) if str(x) in nodes]
        if not ready:
            ready = [n.id for n in graph.nodes if n.type == "start" or (not incoming[n.id] and n.id not in done)]
        if done:
            for nid in nodes:
                if nid in done:
                    continue
                deps = incoming[nid]
                if deps and all(dep in done for dep in deps):
                    ready.append(nid)
        ready = list(dict.fromkeys([x for x in ready if x not in done]))
        final_status = "success"
        final_error: str | None = None
        pause_reason: dict[str, Any] | None = None

        async def ensure_pending_approval(node_id: str, node_name: str | None, request_payload: dict | None) -> str:
            existing = (
                await self.db.execute(
                    select(SkillWorkflowApproval).where(
                        SkillWorkflowApproval.workflow_run_id == run.id,
                        SkillWorkflowApproval.node_id == node_id,
                        SkillWorkflowApproval.status == "pending",
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing.id
            row = SkillWorkflowApproval(
                workflow_run_id=run.id,
                workflow_id=workflow.id,
                user_id=workflow.user_id,
                node_id=node_id,
                node_name=node_name,
                status="pending",
                request_payload=request_payload or {},
            )
            self.db.add(row)
            await self.db.flush()
            return row.id

        async def run_node(node_id: str) -> tuple[str, dict[str, Any]]:
            node = nodes[node_id]
            started = datetime.now(timezone.utc)
            record: dict[str, Any] = {
                "node_id": node.id,
                "node_type": node.type,
                "node_name": node.name or node.id,
                "status": "running",
                "started_at": started.isoformat(),
            }
            cfg = node.config or {}
            try:
                if node.type == "start":
                    record["result"] = input_payload
                    record["status"] = "success"
                    return node_id, record
                if node.type == "condition":
                    left_path = str((cfg.get("left") or "")).strip()
                    op = str((cfg.get("op") or "==")).strip()
                    right = cfg.get("right")
                    left = _resolve_path(left_path, outputs) if left_path else None
                    ok = (left == right) if op == "==" else (left != right)
                    record["result"] = {"condition": ok, "left": left, "right": right, "op": op}
                    record["status"] = "success"
                    return node_id, record
                if node.type == "approval":
                    approvals = input_payload.get("approvals") if isinstance(input_payload, dict) else {}
                    approved = (
                        node.id in approved_nodes
                        or bool(isinstance(approvals, dict) and approvals.get(node.id) is True)
                    )
                    if not approved:
                        approval_id = await ensure_pending_approval(
                            node_id=node.id,
                            node_name=node.name,
                            request_payload={
                                "run_id": run.id,
                                "workflow_id": workflow.id,
                                "node_id": node.id,
                                "node_name": node.name,
                                "node_config": cfg,
                            },
                        )
                        record["status"] = "paused"
                        record["result"] = {
                            "approval_required": True,
                            "approval_id": approval_id,
                        }
                        return node_id, record
                    record["result"] = {"approved": True}
                    record["status"] = "success"
                    return node_id, record
                if node.type == "end":
                    record["result"] = {"output": outputs.get("nodes")}
                    record["status"] = "success"
                    return node_id, record
                if node.type == "merge":
                    sections: dict[str, Any] = {}
                    for src_id in incoming.get(node_id, []):
                        src_node = nodes.get(src_id)
                        label = (src_node.name if src_node and src_node.name else None) or src_id
                        sections[str(label)] = {
                            "node_id": src_id,
                            "result": outputs.get("nodes", {}).get(src_id),
                        }
                    record["result"] = {"sections": sections, "merged": True}
                    record["status"] = "success"
                    return node_id, record

                # skill node
                skill_id = str((cfg.get("skill_id") or "")).strip()
                skill: Skill | None = None
                if skill_id:
                    skill = await self._get_skill(skill_id=skill_id, user_id=workflow.user_id)
                else:
                    skill_name = str((cfg.get("skill_name") or "")).strip()
                    if skill_name:
                        skill = await self._get_skill_by_name(
                            skill_name=skill_name, user_id=workflow.user_id
                        )
                if skill is None:
                    raise RuntimeError(
                        "skill node requires config.skill_id or resolvable config.skill_name"
                    )
                payload_template = cfg.get("payload_template") or {}
                payload = _render_template(payload_template, outputs)
                if not isinstance(payload, dict):
                    payload = {"value": payload}
                retry_count = int(cfg.get("retry_count") or 0)
                timeout_s = int(cfg.get("timeout_seconds") or 0)
                last_error: Exception | None = None
                for _attempt in range(retry_count + 1):
                    try:
                        if timeout_s > 0:
                            raw = await asyncio.wait_for(execute_skill(skill, payload), timeout=timeout_s)
                        else:
                            raw = await execute_skill(skill, payload)
                        result = _to_result_dict(raw)
                        has_error = bool(isinstance(raw, dict) and raw.get("error"))
                        if has_error:
                            raise RuntimeError(str(result.get("error")))
                        record["payload"] = payload
                        record["result"] = result
                        record["status"] = "success"
                        return node_id, record
                    except Exception as e:
                        last_error = e
                raise RuntimeError(str(last_error) if last_error else "skill execution failed")
            except Exception as e:
                record["status"] = "failed"
                record["error"] = str(e)
                return node_id, record
            finally:
                finished = datetime.now(timezone.utc)
                record["finished_at"] = finished.isoformat()
                record["duration_ms"] = _duration_ms(started, finished)

        while ready:
            batch = [nid for nid in ready if nid not in done]
            ready = []
            if not batch:
                break
            results = await asyncio.gather(*[run_node(nid) for nid in batch])
            for node_id, rec in results:
                node_runs.append(rec)
                if rec.get("status") == "paused":
                    pause_reason = {
                        "node_id": node_id,
                        "node_name": rec.get("node_name"),
                        "approval_id": (rec.get("result") or {}).get("approval_id"),
                    }
                    final_status = "paused"
                    final_error = "approval required"
                    outputs["nodes"][node_id] = rec.get("result")
                    ready = []
                    break
                done.add(node_id)
                outputs["nodes"][node_id] = rec.get("result")
                if rec.get("status") == "failed":
                    final_status = "failed"
                    final_error = rec.get("error") or "node failed"
                for edge in outgoing.get(node_id, []):
                    target = edge.target
                    deps = incoming[target]
                    if all(dep in done for dep in deps) and target not in done:
                        target_node = nodes[target]
                        if nodes[node_id].type == "condition":
                            cond = rec.get("result", {}).get("condition")
                            edge_cond = (edge.condition or "default").lower()
                            if edge_cond == "true" and cond is not True:
                                continue
                            if edge_cond == "false" and cond is not False:
                                continue
                        ready.append(target)

        payload = {
            "graph": graph.model_dump(),
            "node_runs": node_runs,
            "outputs": outputs.get("nodes"),
            "engine_state": {
                "done_nodes": sorted(list(done)),
                "outputs": outputs.get("nodes"),
                "ready_nodes": ready,
                "paused": final_status == "paused",
                "pause_reason": pause_reason,
            },
        }
        return final_status, final_error, payload

    async def run_once(
        self, *, workflow_id: str, user_id: str, input_payload: dict | None = None
    ) -> WorkflowRunDetailResponse:
        workflow = await self._get_workflow(workflow_id=workflow_id, user_id=user_id)
        if not workflow.enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow is disabled",
            )
        run = await self.execute_workflow(
            workflow=workflow,
            trigger_type="manual",
            input_payload=input_payload or {},
        )
        return await self.get_run_detail(run_id=run.id, user_id=user_id)

    async def list_pending_approvals(
        self, *, user_id: str, workflow_id: str | None = None, limit: int = 100
    ) -> list[WorkflowApprovalResponse]:
        safe_limit = max(1, min(limit, 500))
        stmt = (
            select(SkillWorkflowApproval)
            .where(
                SkillWorkflowApproval.user_id == user_id,
                SkillWorkflowApproval.status == "pending",
            )
            .order_by(SkillWorkflowApproval.created_at.desc())
            .limit(safe_limit)
        )
        if workflow_id:
            stmt = stmt.where(SkillWorkflowApproval.workflow_id == workflow_id)
        rows = (await self.db.execute(stmt)).scalars().all()
        name_map = await self._workflow_name_map([r.workflow_id for r in rows])
        return [
            WorkflowApprovalResponse(
                id=r.id,
                workflow_run_id=r.workflow_run_id,
                workflow_id=r.workflow_id,
                workflow_name=name_map.get(r.workflow_id, ""),
                node_id=r.node_id,
                node_name=r.node_name,
                status=r.status,
                request_payload=r.request_payload,
                decision_payload=r.decision_payload,
                comment=r.comment,
                created_at=r.created_at,
                decided_at=r.decided_at,
                approved_by=r.approved_by,
            )
            for r in rows
        ]

    async def _decision_approval(
        self,
        *,
        approval_id: str,
        user_id: str,
        decision: str,
        request: WorkflowApprovalDecisionRequest,
    ) -> WorkflowApprovalResponse:
        row = (
            await self.db.execute(
                select(SkillWorkflowApproval).where(
                    SkillWorkflowApproval.id == approval_id,
                    SkillWorkflowApproval.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Approval task not found",
            )
        if row.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approval task is already decided",
            )

        row.status = decision
        row.comment = (request.comment or "").strip() or None
        row.decision_payload = request.decision_payload or {}
        row.approved_by = user_id
        row.decided_at = datetime.now(timezone.utc)
        await self.db.flush()

        run = await self._get_run(run_id=row.workflow_run_id, user_id=user_id)
        workflow = await self._get_workflow(workflow_id=row.workflow_id, user_id=user_id)
        if decision == "rejected":
            run.status = "failed"
            run.error = f"approval rejected at node {row.node_id}"
            run.finished_at = datetime.now(timezone.utc)
            run.duration_ms = _duration_ms(run.started_at, run.finished_at)
            await self._send_alert(
                event="workflow.approval.rejected",
                workflow=workflow,
                run=run,
                message=run.error or "approval rejected",
                extra={"approval_id": row.id, "node_id": row.node_id},
            )
            await self.db.flush()
        elif request.auto_resume:
            await self.resume_run(
                run_id=row.workflow_run_id,
                user_id=user_id,
                request=WorkflowRunResumeRequest(payload={}),
            )

        name_map = await self._workflow_name_map([row.workflow_id])
        return WorkflowApprovalResponse(
            id=row.id,
            workflow_run_id=row.workflow_run_id,
            workflow_id=row.workflow_id,
            workflow_name=name_map.get(row.workflow_id, ""),
            node_id=row.node_id,
            node_name=row.node_name,
            status=row.status,
            request_payload=row.request_payload,
            decision_payload=row.decision_payload,
            comment=row.comment,
            created_at=row.created_at,
            decided_at=row.decided_at,
            approved_by=row.approved_by,
        )

    async def approve_task(
        self, *, approval_id: str, user_id: str, request: WorkflowApprovalDecisionRequest
    ) -> WorkflowApprovalResponse:
        return await self._decision_approval(
            approval_id=approval_id,
            user_id=user_id,
            decision="approved",
            request=request,
        )

    async def reject_task(
        self, *, approval_id: str, user_id: str, request: WorkflowApprovalDecisionRequest
    ) -> WorkflowApprovalResponse:
        return await self._decision_approval(
            approval_id=approval_id,
            user_id=user_id,
            decision="rejected",
            request=request,
        )

    async def resume_run(
        self, *, run_id: str, user_id: str, request: WorkflowRunResumeRequest
    ) -> WorkflowRunDetailResponse:
        run = await self._get_run(run_id=run_id, user_id=user_id)
        if run.status != "paused":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only paused run can be resumed",
            )
        workflow = await self._get_workflow(workflow_id=run.workflow_id, user_id=user_id)
        graph_enabled = bool(
            workflow.graph_json
            and isinstance(workflow.graph_json, dict)
            and workflow.graph_json.get("nodes")
        )
        if not graph_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Run is not graph workflow run",
            )

        merged_payload = dict(run.input_payload or {})
        extra_payload = request.payload or {}
        if isinstance(extra_payload, dict):
            merged_payload.update(extra_payload)
        approval_flags = {
            row.node_id: True for row in run.approvals if row.status == "approved"
        }
        if approval_flags:
            merged_payload["approvals"] = {
                **(merged_payload.get("approvals") or {}),
                **approval_flags,
            }

        resume_state = {}
        if isinstance(run.output_payload, dict):
            resume_state = dict(run.output_payload.get("engine_state") or {})
            resume_state["node_runs"] = list(run.output_payload.get("node_runs") or [])

        run.status = "running"
        run.error = None
        final_status, final_error, output_payload = await self._execute_graph_workflow(
            workflow=workflow,
            run=run,
            input_payload=merged_payload,
            resume_state=resume_state,
            approved_nodes=set(approval_flags.keys()),
        )
        now = datetime.now(timezone.utc)
        run.status = final_status
        run.error = final_error
        run.input_payload = merged_payload
        run.output_payload = output_payload
        if final_status in {"success", "failed"}:
            run.finished_at = now
            run.duration_ms = _duration_ms(run.started_at, now)
        else:
            run.finished_at = None
            run.duration_ms = _duration_ms(run.started_at, now)

        if final_status == "failed":
            await self._send_alert(
                event="workflow.run.failed",
                workflow=workflow,
                run=run,
                message=final_error or "run failed",
                extra={"resume": True},
            )
        await self.db.flush()
        return await self.get_run_detail(run_id=run.id, user_id=user_id)

    async def execute_workflow(
        self,
        *,
        workflow: SkillWorkflow,
        trigger_type: str,
        input_payload: dict,
    ) -> SkillWorkflowRun:
        started_at = datetime.now(timezone.utc)
        run = SkillWorkflowRun(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            trigger_type=trigger_type,
            status="running",
            input_payload=input_payload,
            started_at=started_at,
        )
        self.db.add(run)
        await self.db.flush()

        if workflow.graph_json and isinstance(workflow.graph_json, dict) and workflow.graph_json.get("nodes"):
            final_status, final_error, output_payload = await self._execute_graph_workflow(
                workflow=workflow,
                run=run,
                input_payload=input_payload,
            )
            finished_at = datetime.now(timezone.utc)
            run.status = final_status
            run.error = final_error
            run.output_payload = output_payload
            run.duration_ms = _duration_ms(started_at, finished_at)
            if final_status in {"success", "failed"}:
                run.finished_at = finished_at
            else:
                run.finished_at = None
            if final_status == "failed":
                logger.warning(
                    "workflow graph run failed (alert hook): workflow=%s run=%s error=%s",
                    workflow.id,
                    run.id,
                    final_error,
                )
                await self._send_alert(
                    event="workflow.run.failed",
                    workflow=workflow,
                    run=run,
                    message=final_error or "run failed",
                    extra={"trigger_type": trigger_type},
                )
            await self.db.flush()
            return run

        steps = sorted(
            [s for s in workflow.steps if s.enabled],
            key=lambda x: (x.order_index, x.created_at),
        )
        context: dict[str, Any] = {"input": input_payload, "steps": {}}
        final_status = "success"
        final_error: str | None = None

        for step in steps:
            skill = await self._get_skill(skill_id=step.skill_id, user_id=workflow.user_id)
            step_started = datetime.now(timezone.utc)
            payload = _render_template(step.payload_template or {}, context)
            if not isinstance(payload, dict):
                payload = {"value": payload}

            step_run = SkillWorkflowStepRun(
                workflow_run_id=run.id,
                step_id=step.id,
                skill_id=step.skill_id,
                status="running",
                payload=payload,
                started_at=step_started,
            )
            self.db.add(step_run)
            await self.db.flush()

            try:
                raw_result = await execute_skill(skill, payload)
                result = _to_result_dict(raw_result)
                step_finished = datetime.now(timezone.utc)
                failed = bool(isinstance(raw_result, dict) and raw_result.get("error"))
                step_run.status = "failed" if failed else "success"
                step_run.result = result
                step_run.error = str(result.get("error")) if failed else None
                step_run.finished_at = step_finished
                step_run.duration_ms = _duration_ms(step_started, step_finished)
                context["steps"][step.step_key] = {
                    "status": step_run.status,
                    "payload": payload,
                    "result": result,
                    "error": step_run.error,
                }
                if failed:
                    final_status = "failed"
                    final_error = step_run.error
                    if step.on_error == "stop":
                        break
            except Exception as e:
                step_finished = datetime.now(timezone.utc)
                step_run.status = "failed"
                step_run.error = str(e)
                step_run.finished_at = step_finished
                step_run.duration_ms = _duration_ms(step_started, step_finished)
                context["steps"][step.step_key] = {
                    "status": "failed",
                    "payload": payload,
                    "result": None,
                    "error": step_run.error,
                }
                final_status = "failed"
                final_error = step_run.error
                if step.on_error == "stop":
                    break

            await self.db.flush()

        finished_at = datetime.now(timezone.utc)
        run.status = final_status
        run.error = final_error
        run.output_payload = {"steps": context.get("steps")}
        run.finished_at = finished_at
        run.duration_ms = _duration_ms(started_at, finished_at)
        if final_status != "success":
            logger.warning(
                "workflow run failed (alert hook): workflow=%s run=%s error=%s",
                workflow.id,
                run.id,
                final_error,
            )
            await self._send_alert(
                event="workflow.run.failed",
                workflow=workflow,
                run=run,
                message=final_error or "run failed",
                extra={"trigger_type": trigger_type},
            )
        await self.db.flush()
        return run

    async def list_runs(
        self, *, user_id: str, workflow_id: str | None = None, limit: int = 50
    ) -> list[WorkflowRunResponse]:
        safe_limit = max(1, min(limit, 200))
        stmt = select(SkillWorkflowRun).where(SkillWorkflowRun.user_id == user_id)
        if workflow_id:
            stmt = stmt.where(SkillWorkflowRun.workflow_id == workflow_id)
        stmt = stmt.order_by(SkillWorkflowRun.started_at.desc()).limit(safe_limit)
        result = await self.db.execute(stmt)
        runs = result.scalars().all()

        workflow_ids = [r.workflow_id for r in runs]
        wf_map: dict[str, SkillWorkflow] = {}
        if workflow_ids:
            wf_res = await self.db.execute(
                select(SkillWorkflow).where(SkillWorkflow.id.in_(workflow_ids))  # type: ignore[arg-type]
            )
            wf_map = {w.id: w for w in wf_res.scalars().all()}

        return [
            WorkflowRunResponse(
                id=r.id,
                workflow_id=r.workflow_id,
                workflow_name=(wf_map.get(r.workflow_id).name if wf_map.get(r.workflow_id) else ""),
                trigger_type=r.trigger_type,
                status=r.status,
                input_payload=r.input_payload,
                output_payload=r.output_payload,
                error=r.error,
                started_at=r.started_at,
                finished_at=r.finished_at,
                duration_ms=r.duration_ms,
            )
            for r in runs
        ]

    async def get_run_detail(self, *, run_id: str, user_id: str) -> WorkflowRunDetailResponse:
        run_result = await self.db.execute(
            select(SkillWorkflowRun)
            .where(SkillWorkflowRun.id == run_id, SkillWorkflowRun.user_id == user_id)
            .options(
                selectinload(SkillWorkflowRun.step_runs),
                selectinload(SkillWorkflowRun.approvals),
            )
        )
        run = run_result.scalar_one_or_none()
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow run not found",
            )

        wf_result = await self.db.execute(
            select(SkillWorkflow).where(SkillWorkflow.id == run.workflow_id)
        )
        workflow = wf_result.scalar_one_or_none()

        step_ids = [r.step_id for r in run.step_runs]
        skill_ids = [r.skill_id for r in run.step_runs]

        step_map: dict[str, SkillWorkflowStep] = {}
        if step_ids:
            step_result = await self.db.execute(
                select(SkillWorkflowStep).where(SkillWorkflowStep.id.in_(step_ids))  # type: ignore[arg-type]
            )
            step_map = {s.id: s for s in step_result.scalars().all()}
        skill_map: dict[str, Skill] = {}
        if skill_ids:
            skill_result = await self.db.execute(
                select(Skill).where(Skill.id.in_(skill_ids))  # type: ignore[arg-type]
            )
            skill_map = {s.id: s for s in skill_result.scalars().all()}

        step_runs = sorted(run.step_runs, key=lambda x: x.started_at)
        step_responses = [
            WorkflowStepRunResponse(
                id=sr.id,
                step_id=sr.step_id,
                step_key=(step_map.get(sr.step_id).step_key if step_map.get(sr.step_id) else ""),
                step_name=(step_map.get(sr.step_id).name if step_map.get(sr.step_id) else ""),
                skill_id=sr.skill_id,
                skill_name=(skill_map.get(sr.skill_id).name if skill_map.get(sr.skill_id) else ""),
                status=sr.status,
                payload=sr.payload,
                result=sr.result,
                error=sr.error,
                started_at=sr.started_at,
                finished_at=sr.finished_at,
                duration_ms=sr.duration_ms,
            )
            for sr in step_runs
        ]
        pending_rows = [a for a in run.approvals if a.status == "pending"]
        pending_items = [
            WorkflowApprovalResponse(
                id=a.id,
                workflow_run_id=a.workflow_run_id,
                workflow_id=a.workflow_id,
                workflow_name=(workflow.name if workflow else ""),
                node_id=a.node_id,
                node_name=a.node_name,
                status=a.status,
                request_payload=a.request_payload,
                decision_payload=a.decision_payload,
                comment=a.comment,
                created_at=a.created_at,
                decided_at=a.decided_at,
                approved_by=a.approved_by,
            )
            for a in sorted(pending_rows, key=lambda x: x.created_at)
        ]

        return WorkflowRunDetailResponse(
            id=run.id,
            workflow_id=run.workflow_id,
            workflow_name=(workflow.name if workflow else ""),
            trigger_type=run.trigger_type,
            status=run.status,
            input_payload=run.input_payload,
            output_payload=run.output_payload,
            error=run.error,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_ms=run.duration_ms,
            step_runs=step_responses,
            node_runs=(
                run.output_payload.get("node_runs")
                if isinstance(run.output_payload, dict)
                else None
            ),
            pending_approvals=pending_items,
            can_resume=(run.status == "paused" and len(pending_items) == 0),
        )
