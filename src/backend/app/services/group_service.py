"""Group collaboration service."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupMember, GroupMemoryEntry, GroupMemoryRevision
from app.models.user import User
from app.schemas.group import (
    GroupCreateRequest,
    GroupMemoryCreateRequest,
    GroupMemoryRevisionResponse,
    GroupMemoryResponse,
    GroupMemoryUpdateRequest,
    GroupMemberResponse,
    GroupMemberUpsertRequest,
    GroupResponse,
    GroupUpdateRequest,
)
from app.services.llm_credentials import get_accessible_ai_config


def resolve_devbridge_project_allowlists(group: Group) -> dict[str, list[str]] | None:
    """Normalize per-provider devbridge allowlists (strict whitelist when set)."""
    raw = group.devbridge_project_allowlists
    if isinstance(raw, dict):
        if not raw:
            return None
        return {
            str(provider): [str(slug).strip() for slug in (slugs or []) if str(slug).strip()]
            for provider, slugs in raw.items()
        }
    legacy = group.gamecenter_project_allowlist
    if legacy is not None:
        return {
            "gamecenter": [str(slug).strip() for slug in legacy if str(slug).strip()],
        }
    return None


def _group_response(group: Group, **extra) -> GroupResponse:
    payload = dict(
        id=group.id,
        name=group.name,
        description=group.description,
        owner_user_id=group.owner_user_id,
        default_skill_ids=group.default_skill_ids,
        ai_config_id=group.ai_config_id,
        devbridge_project_allowlists=resolve_devbridge_project_allowlists(group),
        created_at=group.created_at,
        updated_at=group.updated_at,
        member_count=len(group.members or []),
    )
    payload.update(extra)
    return GroupResponse(**payload)


def _member_response(member: GroupMember, user: User | None = None) -> GroupMemberResponse:
    return GroupMemberResponse(
        id=member.id,
        user_id=member.user_id,
        username=user.username if user else None,
        display_name=user.display_name if user else None,
        user_role=user.role if user else None,
        role=member.role,
        created_at=member.created_at,
    )


def _memory_response(entry: GroupMemoryEntry) -> GroupMemoryResponse:
    return GroupMemoryResponse(
        id=entry.id,
        group_id=entry.group_id,
        memory_type=entry.memory_type,
        title=entry.title,
        content=entry.content,
        tags=entry.tags,
        topic=entry.topic,
        status=entry.status,
        created_by=entry.created_by,
        updated_by=entry.updated_by,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _revision_response(revision: GroupMemoryRevision) -> GroupMemoryRevisionResponse:
    return GroupMemoryRevisionResponse(
        id=revision.id,
        entry_id=revision.entry_id,
        version=revision.version,
        title=revision.title,
        content=revision.content,
        tags=revision.tags,
        topic=revision.topic,
        status=revision.status,
        edited_by=revision.edited_by,
        created_at=revision.created_at,
    )


class GroupService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_membership(self, group_id: str, user_id: str) -> GroupMember | None:
        result = await self.db.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def require_group_role(
        self,
        group_id: str,
        user_id: str,
        *,
        allowed_roles: tuple[str, ...] = ("member", "editor", "owner"),
    ) -> GroupMember:
        membership = await self.get_membership(group_id, user_id)
        if membership is None or membership.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Group access denied",
            )
        return membership

    async def list_groups_for_user(self, user_id: str) -> list[GroupResponse]:
        result = await self.db.execute(
            select(Group, GroupMember)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id)
            .order_by(Group.updated_at.desc())
        )
        rows = result.all()
        items: list[GroupResponse] = []
        for group, membership in rows:
            items.append(_group_response(group, current_user_role=membership.role))
        return items

    async def list_groups(self) -> list[GroupResponse]:
        result = await self.db.execute(select(Group).order_by(Group.updated_at.desc()))
        groups = result.scalars().all()
        return [_group_response(group) for group in groups]

    async def create_group(self, actor_id: str, data: GroupCreateRequest) -> GroupResponse:
        if data.ai_config_id and await get_accessible_ai_config(
            self.db, data.ai_config_id, actor_id
        ) is None:
            raise HTTPException(status_code=404, detail="AI config not found")
        group = Group(
            name=data.name.strip(),
            description=(data.description or "").strip() or None,
            owner_user_id=actor_id,
            default_skill_ids=data.default_skill_ids,
            ai_config_id=data.ai_config_id or None,
            devbridge_project_allowlists=data.devbridge_project_allowlists,
        )
        self.db.add(group)
        await self.db.flush()
        member = GroupMember(group_id=group.id, user_id=actor_id, role="owner")
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(group)
        return _group_response(group, current_user_role="owner", member_count=1)

    async def update_group(
        self,
        group_id: str,
        actor_id: str,
        data: GroupUpdateRequest,
    ) -> GroupResponse:
        group = await self.db.get(Group, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")
        fields = data.model_dump(exclude_unset=True)
        if "name" in fields and fields["name"] is not None:
            group.name = str(fields["name"]).strip()
        if "description" in fields:
            group.description = (str(fields["description"] or "").strip() or None)
        if "default_skill_ids" in fields:
            group.default_skill_ids = fields["default_skill_ids"]
        if "ai_config_id" in fields:
            if fields["ai_config_id"] and await get_accessible_ai_config(
                self.db, fields["ai_config_id"], actor_id
            ) is None:
                raise HTTPException(status_code=404, detail="AI config not found")
            group.ai_config_id = fields["ai_config_id"] or None
        if "devbridge_project_allowlists" in fields:
            group.devbridge_project_allowlists = fields["devbridge_project_allowlists"]
            group.gamecenter_project_allowlist = None
        await self.db.flush()
        await self.db.refresh(group)
        return _group_response(group)

    async def delete_group(self, group_id: str) -> None:
        group = await self.db.get(Group, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")
        await self.db.delete(group)
        await self.db.flush()

    async def list_members(self, group_id: str, user_id: str) -> list[GroupMemberResponse]:
        await self.require_group_role(group_id, user_id)
        result = await self.db.execute(
            select(GroupMember, User)
            .join(User, User.id == GroupMember.user_id)
            .where(GroupMember.group_id == group_id)
            .order_by(GroupMember.created_at.asc())
        )
        return [_member_response(member, user) for member, user in result.all()]

    async def upsert_member(self, group_id: str, request: GroupMemberUpsertRequest) -> GroupMemberResponse:
        group = await self.db.get(Group, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")
        user = await self.db.get(User, request.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        existing = await self.get_membership(group_id, request.user_id)
        if existing is None:
            existing = GroupMember(group_id=group_id, user_id=request.user_id, role=request.role)
            self.db.add(existing)
            await self.db.flush()
        else:
            existing.role = request.role
            await self.db.flush()
        await self.db.refresh(existing)
        return _member_response(existing, user)

    async def remove_member(self, group_id: str, member_user_id: str) -> None:
        membership = await self.get_membership(group_id, member_user_id)
        if membership is None:
            raise HTTPException(status_code=404, detail="Group member not found")
        await self.db.delete(membership)
        await self.db.flush()

    async def list_memories(self, group_id: str, user_id: str) -> list[GroupMemoryResponse]:
        await self.require_group_role(group_id, user_id)
        result = await self.db.execute(
            select(GroupMemoryEntry)
            .where(GroupMemoryEntry.group_id == group_id)
            .order_by(GroupMemoryEntry.updated_at.desc())
        )
        return [_memory_response(entry) for entry in result.scalars().all()]

    async def create_memory(
        self,
        group_id: str,
        user_id: str,
        data: GroupMemoryCreateRequest,
    ) -> GroupMemoryResponse:
        await self.require_group_role(group_id, user_id, allowed_roles=("editor", "owner"))
        entry = GroupMemoryEntry(
            group_id=group_id,
            memory_type=data.memory_type,
            title=data.title.strip(),
            content=data.content.strip(),
            tags=data.tags,
            topic=(data.topic or "").strip() or None,
            status=data.status,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(entry)
        await self.db.flush()
        revision = GroupMemoryRevision(
            entry_id=entry.id,
            version=1,
            title=entry.title,
            content=entry.content,
            tags=entry.tags,
            topic=entry.topic,
            status=entry.status,
            edited_by=user_id,
        )
        self.db.add(revision)
        await self.db.flush()
        await self.db.refresh(entry)
        return _memory_response(entry)

    async def update_memory(
        self,
        group_id: str,
        memory_id: str,
        user_id: str,
        data: GroupMemoryUpdateRequest,
    ) -> GroupMemoryResponse:
        await self.require_group_role(group_id, user_id, allowed_roles=("editor", "owner"))
        entry = await self.db.get(GroupMemoryEntry, memory_id)
        if entry is None or entry.group_id != group_id:
            raise HTTPException(status_code=404, detail="Group memory not found")
        fields = data.model_dump(exclude_unset=True)
        for key, value in fields.items():
            if key in {"title", "content", "topic"} and value is not None:
                value = str(value).strip()
                value = value or None if key == "topic" else value
            setattr(entry, key, value)
        entry.updated_by = user_id
        entry.updated_at = datetime.now(timezone.utc)
        version_result = await self.db.execute(
            select(func.max(GroupMemoryRevision.version)).where(GroupMemoryRevision.entry_id == entry.id)
        )
        next_version = int(version_result.scalar() or 0) + 1
        self.db.add(
            GroupMemoryRevision(
                entry_id=entry.id,
                version=next_version,
                title=entry.title,
                content=entry.content,
                tags=entry.tags,
                topic=entry.topic,
                status=entry.status,
                edited_by=user_id,
            )
        )
        await self.db.flush()
        await self.db.refresh(entry)
        return _memory_response(entry)

    async def delete_memory(self, group_id: str, memory_id: str, user_id: str) -> None:
        await self.require_group_role(group_id, user_id, allowed_roles=("editor", "owner"))
        entry = await self.db.get(GroupMemoryEntry, memory_id)
        if entry is None or entry.group_id != group_id:
            raise HTTPException(status_code=404, detail="Group memory not found")
        await self.db.delete(entry)
        await self.db.flush()

    async def list_memory_revisions(
        self,
        group_id: str,
        memory_id: str,
        user_id: str,
    ) -> list[GroupMemoryRevisionResponse]:
        await self.require_group_role(group_id, user_id)
        entry = await self.db.get(GroupMemoryEntry, memory_id)
        if entry is None or entry.group_id != group_id:
            raise HTTPException(status_code=404, detail="Group memory not found")
        result = await self.db.execute(
            select(GroupMemoryRevision)
            .where(GroupMemoryRevision.entry_id == memory_id)
            .order_by(GroupMemoryRevision.version.desc())
        )
        return [_revision_response(revision) for revision in result.scalars().all()]

    async def group_knowledge_base_ids(self, group_id: str) -> list[str]:
        from app.models.knowledge import KnowledgeBase

        result = await self.db.execute(
            select(KnowledgeBase.id)
            .where(KnowledgeBase.group_id == group_id, KnowledgeBase.enabled == True)
            .order_by(KnowledgeBase.created_at.asc())
        )
        return [str(row[0]) for row in result.all()]

    async def relevant_memories_for_query(
        self,
        group_id: str,
        query: str,
        *,
        limit: int = 3,
    ) -> list[GroupMemoryEntry]:
        result = await self.db.execute(
            select(GroupMemoryEntry)
            .where(
                GroupMemoryEntry.group_id == group_id,
                GroupMemoryEntry.status.in_(["verified", "draft"]),
            )
            .order_by(GroupMemoryEntry.updated_at.desc())
            .limit(30)
        )
        entries = list(result.scalars().all())
        terms = [part.strip().lower() for part in query.split() if part.strip()]
        if not terms:
            return entries[:limit]

        def _score(entry: GroupMemoryEntry) -> int:
            haystacks = [
                (entry.title or "").lower(),
                (entry.topic or "").lower(),
                " ".join(str(tag).lower() for tag in (entry.tags or [])),
                (entry.content or "").lower()[:2000],
            ]
            score = 0
            for term in terms[:8]:
                for hay in haystacks:
                    if term and term in hay:
                        score += 1
            return score

        ranked = sorted(entries, key=_score, reverse=True)
        filtered = [entry for entry in ranked if _score(entry) > 0]
        return (filtered or ranked)[:limit]
