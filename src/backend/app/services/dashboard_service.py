"""Dashboard statistics service — computed KPIs and trends."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.models.knowledge import Document, KnowledgeBase
from app.models.message import Message
from app.models.skill import Skill
from app.schemas.dashboard import (
    AgentStats,
    AgentStatsResponse,
    DashboardActivity,
    DashboardStatsResponse,
    DashboardTrends,
    StatsOverviewResponse,
    TrendDatapoint,
    TrendsResponse,
)


class DashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_stats(self, user_id: str | None = None) -> DashboardStatsResponse:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        total_conv_stmt = select(func.count()).select_from(Conversation)
        active_conv_stmt = select(func.count()).select_from(Conversation).where(
            Conversation.status == "active"
        )
        total_agents_stmt = select(func.count()).select_from(CustomerConfig)
        total_docs_stmt = select(func.count()).select_from(Document).join(KnowledgeBase)
        total_skills_stmt = select(func.count()).select_from(Skill)
        messages_today_stmt = (
            select(func.count())
            .select_from(Message)
            .join(Conversation)
            .where(Message.created_at >= today_start)
        )

        if user_id is not None:
            total_conv_stmt = total_conv_stmt.where(Conversation.user_id == user_id)
            active_conv_stmt = active_conv_stmt.where(Conversation.user_id == user_id)
            total_agents_stmt = total_agents_stmt.where(CustomerConfig.user_id == user_id)
            total_docs_stmt = total_docs_stmt.where(KnowledgeBase.user_id == user_id)
            total_skills_stmt = total_skills_stmt.where(Skill.user_id == user_id)
            messages_today_stmt = messages_today_stmt.where(Conversation.user_id == user_id)

        total_conv = await self._scalar_count(total_conv_stmt)
        active_conv = await self._scalar_count(active_conv_stmt)
        total_agents = await self._scalar_count(total_agents_stmt)
        total_docs = await self._scalar_count(total_docs_stmt)
        total_skills = await self._scalar_count(total_skills_stmt)
        messages_today = await self._scalar_count(messages_today_stmt)

        return DashboardStatsResponse(
            total_conversations=total_conv,
            active_conversations=active_conv,
            total_agents=total_agents,
            total_documents=total_docs,
            total_skills=total_skills,
            messages_today=messages_today,
            avg_response_time=0,
            satisfaction_rate=0,
            trends=DashboardTrends(),
        )

    async def get_overview(self, user_id: str | None = None, period_days: int = 30) -> StatsOverviewResponse:
        """Compute overview KPIs: totals, FRT, ART, resolution rate."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_start = now - timedelta(days=period_days)

        total_conv_stmt = select(func.count()).select_from(Conversation)
        active_conv_stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.status == "active")
        )
        closed_conv_stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.created_at >= period_start,
                Conversation.status == "closed",
            )
        )
        period_total_stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.created_at >= period_start)
        )
        if user_id is not None:
            total_conv_stmt = total_conv_stmt.where(Conversation.user_id == user_id)
            active_conv_stmt = active_conv_stmt.where(Conversation.user_id == user_id)
            closed_conv_stmt = closed_conv_stmt.where(Conversation.user_id == user_id)
            period_total_stmt = period_total_stmt.where(Conversation.user_id == user_id)

        total_conv = await self._scalar_count(total_conv_stmt)
        active_conv = await self._scalar_count(active_conv_stmt)
        closed_conv = await self._scalar_count(closed_conv_stmt)
        period_total = await self._scalar_count(period_total_stmt)

        resolution_rate = (closed_conv / period_total) if period_total > 0 else 0.0

        total_messages = await self._scalar_count(
            select(func.count()).select_from(Message).join(Conversation)
            .where(Conversation.user_id == user_id) if user_id
            else select(func.count()).select_from(Message)
        )

        messages_today_stmt = (
            select(func.count())
            .select_from(Message)
            .join(Conversation)
            .where(Message.created_at >= today_start)
        )
        if user_id is not None:
            messages_today_stmt = messages_today_stmt.where(
                Conversation.user_id == user_id
            )
        messages_today = await self._scalar_count(messages_today_stmt)

        total_agents = await self._scalar_count(
            select(func.count()).select_from(CustomerConfig).where(CustomerConfig.user_id == user_id)
            if user_id else select(func.count()).select_from(CustomerConfig)
        )
        total_docs = await self._scalar_count(
            select(func.count()).select_from(Document).join(KnowledgeBase).where(KnowledgeBase.user_id == user_id)
            if user_id else select(func.count()).select_from(Document)
        )
        total_skills = await self._scalar_count(
            select(func.count()).select_from(Skill).where(Skill.user_id == user_id)
            if user_id else select(func.count()).select_from(Skill)
        )

        frt = await self._compute_frt(user_id, period_start)
        art = await self._compute_art(user_id, period_start)

        return StatsOverviewResponse(
            total_conversations=total_conv,
            active_conversations=active_conv,
            closed_conversations=closed_conv,
            total_messages=total_messages,
            messages_today=messages_today,
            total_agents=total_agents,
            total_documents=total_docs,
            total_skills=total_skills,
            first_response_time_avg_seconds=frt,
            avg_response_time_seconds=art,
            resolution_rate=round(resolution_rate, 4),
        )

    async def get_trends(
        self, user_id: str | None = None, metric: str = "messages", days: int = 30
    ) -> TrendsResponse:
        """Get daily time-series for messages, conversations, or documents."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)

        if metric == "messages":
            stmt = (
                select(func.date(Message.created_at).label("day"), func.count().label("cnt"))
                .join(Conversation)
                .where(Message.created_at >= start)
            )
            if user_id is not None:
                stmt = stmt.where(Conversation.user_id == user_id)
            stmt = stmt.group_by(text("day")).order_by(text("day"))
        elif metric == "conversations":
            stmt = (
                select(func.date(Conversation.created_at).label("day"), func.count().label("cnt"))
                .where(Conversation.created_at >= start)
            )
            if user_id is not None:
                stmt = stmt.where(Conversation.user_id == user_id)
            stmt = stmt.group_by(text("day")).order_by(text("day"))
        else:
            stmt = (
                select(func.date(Document.created_at).label("day"), func.count().label("cnt"))
                .join(KnowledgeBase)
                .where(Document.created_at >= start)
            )
            if user_id is not None:
                stmt = stmt.where(KnowledgeBase.user_id == user_id)
            stmt = stmt.group_by(text("day")).order_by(text("day"))

        result = await self.db.execute(stmt)
        rows = list(result.all())

        data_map = {str(row[0]): int(row[1] or 0) for row in rows}

        data = []
        for i in range(days):
            d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            data.append(TrendDatapoint(date=d, count=data_map.get(d, 0)))

        return TrendsResponse(metric=metric, days=days, data=data)

    async def get_agent_stats(self, user_id: str | None = None) -> AgentStatsResponse:
        """Get per-agent (customer config) performance stats."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        stmt = select(CustomerConfig)
        if user_id is not None:
            stmt = stmt.where(CustomerConfig.user_id == user_id)
        result = await self.db.execute(stmt)
        customers = list(result.scalars().all())

        agent_stats: list[AgentStats] = []
        for c in customers:
            total_conv = await self._scalar_count(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.customer_id == c.id)
            )
            active_conv = await self._scalar_count(
                select(func.count())
                .select_from(Conversation)
                .where(
                    Conversation.customer_id == c.id,
                    Conversation.status == "active",
                )
            )
            msgs_today = await self._scalar_count(
                select(func.count()).select_from(Message).join(Conversation)
                .where(Conversation.customer_id == c.id, Message.created_at >= today_start)
            )
            art = await self._compute_art_for_customer(c.id)

            agent_stats.append(AgentStats(
                customer_id=c.id,
                customer_name=c.name,
                total_conversations=total_conv,
                active_conversations=active_conv,
                messages_today=msgs_today,
                avg_response_time_seconds=art,
            ))

        return AgentStatsResponse(agents=agent_stats)

    async def get_activities(
        self, user_id: str | None = None, limit: int = 10
    ) -> list[DashboardActivity]:
        activities: list[DashboardActivity] = []

        conv_stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
        if user_id is not None:
            conv_stmt = conv_stmt.where(Conversation.user_id == user_id)
        conv_result = await self.db.execute(conv_stmt)
        for conv in conv_result.scalars().all():
            title = conv.title or "New conversation"
            activities.append(
                DashboardActivity(
                    id=conv.id,
                    type="conversation",
                    description=f"Conversation: {title}",
                    timestamp=conv.updated_at,
                )
            )

        doc_stmt = (
            select(Document)
            .join(KnowledgeBase)
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        if user_id is not None:
            doc_stmt = doc_stmt.where(KnowledgeBase.user_id == user_id)
        doc_result = await self.db.execute(doc_stmt)
        for doc in doc_result.scalars().all():
            activities.append(
                DashboardActivity(
                    id=doc.id,
                    type="document",
                    description=f"Document: {doc.title}",
                    timestamp=doc.created_at,
                )
            )

        activities.sort(key=lambda a: a.timestamp, reverse=True)
        return activities[:limit]

    def _epoch_diff(self, a, b):
        """Return SQL expression for (a - b) in seconds, dialect-aware."""
        dialect = self.db.get_bind().dialect.name
        if dialect == "mysql":
            return func.unix_timestamp(a) - func.unix_timestamp(b)
        elif dialect == "sqlite":
            return func.strftime("%s", a) - func.strftime("%s", b)
        else:
            return func.extract("epoch", a) - func.extract("epoch", b)

    async def _compute_frt(self, user_id: str | None, period_start: datetime) -> float | None:
        """Average First Response Time: conversation.created_at to first assistant message."""
        sub = (
            select(
                Conversation.id.label("conv_id"),
                Conversation.created_at.label("conv_created"),
                func.min(Message.created_at).label("first_assistant"),
            )
            .join(Message, Message.conversation_id == Conversation.id)
            .where(
                Message.role == "assistant",
                Conversation.created_at >= period_start,
            )
            .group_by(Conversation.id)
        )
        if user_id is not None:
            sub = sub.where(Conversation.user_id == user_id)

        result = await self.db.execute(select(func.avg(
            self._epoch_diff(sub.c.first_assistant, sub.c.conv_created)
        )).select_from(sub.subquery()))
        val = result.scalar()
        return float(val) if val is not None else None

    async def _compute_art(self, user_id: str | None, period_start: datetime) -> float | None:
        """Average Response Time: user message → next assistant message gap."""
        # Get all user+assistant message pairs within conversations
        user_stmt = select(Message).join(Conversation).where(
            Message.role == "user",
            Message.created_at >= period_start,
        )
        if user_id is not None:
            user_stmt = user_stmt.where(Conversation.user_id == user_id)

        user_result = await self.db.execute(user_stmt.order_by(Message.conversation_id, Message.created_at))
        user_msgs = list(user_result.scalars().all())

        if not user_msgs:
            return None

        total_gap = 0.0
        count = 0
        for um in user_msgs:
            next_assistant = await self.db.execute(
                select(func.min(Message.created_at))
                .where(
                    Message.conversation_id == um.conversation_id,
                    Message.role == "assistant",
                    Message.created_at > um.created_at,
                )
            )
            next_at = next_assistant.scalar()
            if next_at is not None:
                total_gap += (next_at - um.created_at).total_seconds()
                count += 1

        return total_gap / count if count > 0 else None

    async def _compute_art_for_customer(self, customer_id: str) -> float | None:
        """Average response time for a specific customer config."""
        conv_ids_result = await self.db.execute(
            select(Conversation.id).where(Conversation.customer_id == customer_id)
        )
        conv_ids = [row[0] for row in conv_ids_result.all()]
        if not conv_ids:
            return None

        total_gap = 0.0
        count = 0
        for cid in conv_ids:
            user_result = await self.db.execute(
                select(Message).where(
                    Message.conversation_id == cid, Message.role == "user"
                ).order_by(Message.created_at)
            )
            for um in user_result.scalars().all():
                next_result = await self.db.execute(
                    select(func.min(Message.created_at))
                    .where(
                        Message.conversation_id == cid,
                        Message.role == "assistant",
                        Message.created_at > um.created_at,
                    )
                )
                next_at = next_result.scalar()
                if next_at is not None:
                    total_gap += (next_at - um.created_at).total_seconds()
                    count += 1

        return total_gap / count if count > 0 else None

    async def _scalar_count(self, stmt) -> int:
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)
