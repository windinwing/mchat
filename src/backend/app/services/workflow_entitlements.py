"""Plan-based limits for workflow orchestration and schedules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_template import ChannelTemplate
from app.models.customer import CustomerConfig
from app.models.user import User
from app.models.skill_schedule import SkillSchedule
from app.models.workflow import SkillWorkflow, SkillWorkflowRun
from app.schemas.workflow_entitlements import WorkflowEntitlementsResponse
from app.services.subscription_gate import is_subscription_active

PLAN_RANK: dict[str, int] = {
    "free": 0,
    "free_trial": 1,
    "pro": 2,
    "enterprise": 3,
}

PLAN_LABELS: dict[str, str] = {
    "free": "免费版",
    "free_trial": "试用版",
    "pro": "Pro",
    "enterprise": "企业版",
}


@dataclass(frozen=True)
class AutomationLimits:
    max_workflows: int | None
    max_schedules: int | None
    max_runs_month: int | None
    dag_enabled: bool
    channel_triggers_enabled: bool


AUTOMATION_LIMITS: dict[str, AutomationLimits] = {
    "free": AutomationLimits(
        max_workflows=0,
        max_schedules=0,
        max_runs_month=0,
        dag_enabled=False,
        channel_triggers_enabled=False,
    ),
    "free_trial": AutomationLimits(
        max_workflows=3,
        max_schedules=2,
        max_runs_month=50,
        dag_enabled=True,
        channel_triggers_enabled=True,
    ),
    "pro": AutomationLimits(
        max_workflows=30,
        max_schedules=15,
        max_runs_month=500,
        dag_enabled=True,
        channel_triggers_enabled=True,
    ),
    "enterprise": AutomationLimits(
        max_workflows=None,
        max_schedules=None,
        max_runs_month=None,
        dag_enabled=True,
        channel_triggers_enabled=True,
    ),
}


def limits_for_plan(plan: str | None) -> AutomationLimits:
    key = (plan or "free").strip().lower()
    return AUTOMATION_LIMITS.get(key, AUTOMATION_LIMITS["free"])


def _effective_channel_plan(channel: CustomerConfig, *, now: datetime) -> str:
    active = is_subscription_active(
        plan=channel.plan or "free",
        trial_ends_at=channel.trial_ends_at,
        subscription_ends_at=channel.subscription_ends_at,
        now=now,
    )
    if not active:
        return "free"
    return (channel.plan or "free").strip().lower()


async def effective_automation_plan(
    db: AsyncSession, user: User
) -> tuple[str, list[CustomerConfig]]:
    if user.role in ("admin", "agent"):
        return "enterprise", []
    result = await db.execute(
        select(CustomerConfig).where(CustomerConfig.user_id == user.id)
    )
    channels = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    best = "free"
    for ch in channels:
        tier = _effective_channel_plan(ch, now=now)
        if PLAN_RANK.get(tier, 0) > PLAN_RANK.get(best, 0):
            best = tier
    return best, channels


async def _pick_upgrade_target(
    db: AsyncSession,
    channels: list[CustomerConfig],
    plan: str,
) -> tuple[str | None, str | None, str | None, int | None]:
    """Channel + template for automation checkout (renew user's workspace plan)."""
    if plan in ("pro", "enterprise"):
        return None, None, None, None
    if not channels:
        return None, None, None, None

    template_ids = {ch.template_id for ch in channels if ch.template_id}
    templates: dict[str, ChannelTemplate] = {}
    if template_ids:
        t_result = await db.execute(
            select(ChannelTemplate).where(ChannelTemplate.id.in_(template_ids))
        )
        templates = {t.id: t for t in t_result.scalars().all()}

    def _tpl_price(tpl: ChannelTemplate | None) -> int:
        if tpl is None:
            return 0
        return int(tpl.price_monthly_cents or 0)

    ranked: list[tuple[CustomerConfig, ChannelTemplate | None, int]] = []
    for ch in channels:
        tpl = templates.get(ch.template_id) if ch.template_id else None
        ranked.append((ch, tpl, _tpl_price(tpl)))

    patent = [
        (ch, tpl, price)
        for ch, tpl, price in ranked
        if tpl and (tpl.category or "") == "patent_rag"
    ]
    if patent:
        ch, tpl, price = patent[0]
        return ch.id, ch.template_id, tpl.name if tpl else None, price

    paid = [(ch, tpl, price) for ch, tpl, price in ranked if price > 0]
    if paid:
        ch, tpl, price = max(paid, key=lambda x: x[2])
        return ch.id, ch.template_id, tpl.name if tpl else None, price

    ch, tpl, price = ranked[0]
    return ch.id, ch.template_id, tpl.name if tpl else None, price


def _under_cap(current: int, cap: int | None) -> bool:
    return cap is None or current < cap


async def _count_workflows(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(SkillWorkflow).where(
            SkillWorkflow.user_id == user_id
        )
    )
    return int(result.scalar() or 0)


async def _count_schedules(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(SkillSchedule).where(
            SkillSchedule.user_id == user_id
        )
    )
    return int(result.scalar() or 0)


async def _count_runs_this_month(db: AsyncSession, user_id: str) -> int:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count())
        .select_from(SkillWorkflowRun)
        .where(
            SkillWorkflowRun.user_id == user_id,
            SkillWorkflowRun.started_at >= month_start,
        )
    )
    return int(result.scalar() or 0)


async def get_workflow_entitlements(
    db: AsyncSession, user: User
) -> WorkflowEntitlementsResponse:
    plan, channels = await effective_automation_plan(db, user)
    limits = limits_for_plan(plan)
    wf_count = await _count_workflows(db, user.id)
    sched_count = await _count_schedules(db, user.id)
    runs_month = await _count_runs_this_month(db, user.id)
    upgrade_ch, upgrade_tpl, upgrade_name, upgrade_cents = await _pick_upgrade_target(
        db, channels, plan
    )
    upgrade_required = plan in ("free",) or (
        plan == "free_trial"
        and not _under_cap(wf_count, limits.max_workflows)
    )
    upgrade_instant = bool(
        upgrade_required
        and upgrade_ch
        and (upgrade_cents is None or upgrade_cents <= 0)
    )
    return WorkflowEntitlementsResponse(
        plan=plan,
        max_workflows=limits.max_workflows,
        max_schedules=limits.max_schedules,
        max_runs_month=limits.max_runs_month,
        dag_enabled=limits.dag_enabled,
        channel_triggers_enabled=limits.channel_triggers_enabled,
        workflow_count=wf_count,
        schedule_count=sched_count,
        runs_month=runs_month,
        can_create_workflow=_under_cap(wf_count, limits.max_workflows)
        and limits.max_workflows != 0,
        can_create_schedule=_under_cap(sched_count, limits.max_schedules)
        and limits.max_schedules != 0,
        can_run_workflow=(
            limits.max_runs_month is None
            or (
                limits.max_runs_month > 0
                and _under_cap(runs_month, limits.max_runs_month)
            )
        ),
        upgrade_required=upgrade_required and user.role == "user",
        upgrade_template_id=upgrade_tpl,
        upgrade_channel_id=upgrade_ch,
        upgrade_template_name=upgrade_name,
        upgrade_amount_cents=upgrade_cents,
        upgrade_instant=upgrade_instant,
        upgrade_purpose="automation",
        plan_label=PLAN_LABELS.get(plan, plan),
    )


def _limit_error(
    *,
    code: str,
    message: str,
    ent: WorkflowEntitlementsResponse,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "code": code,
            "message": message,
            "plan": ent.plan,
            "upgrade_template_id": ent.upgrade_template_id,
            "upgrade_channel_id": ent.upgrade_channel_id,
        },
    )


async def ensure_can_create_workflow(db: AsyncSession, user: User) -> None:
    ent = await get_workflow_entitlements(db, user)
    if ent.can_create_workflow:
        return
    if ent.max_workflows == 0:
        raise _limit_error(
            code="workflow_plan_required",
            message="工作流编排需开通试用或 Pro 权益，请在工作流页点击「开通工作流编排」",
            ent=ent,
        )
    raise _limit_error(
        code="workflow_limit",
        message=f"已达工作流数量上限（{ent.workflow_count}/{ent.max_workflows}）",
        ent=ent,
    )


async def ensure_can_create_schedule(db: AsyncSession, user: User) -> None:
    ent = await get_workflow_entitlements(db, user)
    if ent.can_create_schedule:
        return
    if ent.max_schedules == 0:
        raise _limit_error(
            code="schedule_plan_required",
            message="定时任务需 Pro 或试用版套餐",
            ent=ent,
        )
    raise _limit_error(
        code="schedule_limit",
        message=f"已达定时任务数量上限（{ent.schedule_count}/{ent.max_schedules}）",
        ent=ent,
    )


async def ensure_can_run_workflow(db: AsyncSession, user: User) -> None:
    ent = await get_workflow_entitlements(db, user)
    if ent.can_run_workflow:
        return
    if (ent.max_runs_month or 0) == 0:
        raise _limit_error(
            code="workflow_run_plan_required",
            message="运行工作流需 Pro 或试用版套餐",
            ent=ent,
        )
    raise _limit_error(
        code="workflow_run_limit",
        message=f"本月运行次数已用尽（{ent.runs_month}/{ent.max_runs_month}）",
        ent=ent,
    )


async def ensure_can_save_dag(db: AsyncSession, user: User) -> None:
    ent = await get_workflow_entitlements(db, user)
    if ent.dag_enabled:
        return
    raise _limit_error(
        code="workflow_dag_plan_required",
        message="图形编排需 Pro 或试用版套餐",
        ent=ent,
    )
