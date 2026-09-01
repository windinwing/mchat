"""Skill draft lifecycle: chat → preview → commit to tenant skills/."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.customer import CustomerConfig
from app.models.message import Message
from app.models.user import User
from app.schemas.skill_draft import SkillDraftFileEntry, SkillDraftResponse
from app.services.llm_json import llm_complete_json
from app.services.skill_filter import filter_tenant_skill_ids
from app.services.skill_service import SkillService
from app.workspace.paths import ensure_execution_layout, resolve_workspace_root, safe_workspace_segment, tenant_root

_DRAFTS_REL = Path("data") / ".mchat" / "skill-drafts"

_SKILL_DRAFT_SYSTEM = """You are an expert MChat skill author. Given a chat transcript, produce a skill package as JSON.

Return ONLY a JSON object with keys:
- name: short slug (lowercase, hyphens, max 40 chars)
- description: one-line summary
- skill_type: one of tool, function, webhook (prefer tool)
- files: object mapping relative paths to file contents

Required file: SKILL.md with YAML frontmatter:
---
name: <name>
description: "<description>"
type: <skill_type>
---

Then markdown instructions for when/how to use the skill.

Optional: main.py for executable tool skills (must expose run(args) or similar).

Keep files minimal and self-contained. Do not include secrets or placeholder API keys.
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _drafts_root(user_id: str) -> Path:
    root = tenant_root(user_id)
    ensure_execution_layout(root)
    drafts = root / _DRAFTS_REL
    drafts.mkdir(parents=True, exist_ok=True)
    return drafts


def _group_drafts_root(group_id: str) -> Path:
    gid = safe_workspace_segment(group_id)
    if not gid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid group id",
        )
    root = resolve_workspace_root() / "_groups" / gid / "data" / ".mchat" / "skill-drafts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _group_skills_root(group_id: str) -> Path:
    gid = safe_workspace_segment(group_id)
    if not gid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid group id",
        )
    root = resolve_workspace_root() / "_groups" / gid / "skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _manifest_path(user_id: str, draft_id: str, group_id: str | None = None) -> Path:
    base = _group_drafts_root(group_id) if group_id else _drafts_root(user_id)
    return base / draft_id / "manifest.json"


def _files_dir(user_id: str, draft_id: str, group_id: str | None = None) -> Path:
    base = _group_drafts_root(group_id) if group_id else _drafts_root(user_id)
    return base / draft_id / "files"


def _safe_relative_path(raw: str) -> str | None:
    segment = (raw or "").strip().replace("\\", "/").lstrip("/")
    if not segment or ".." in segment.split("/"):
        return None
    return segment


class SkillDraftService:
    async def _require_group_editor(self, group_id: str, user_id: str) -> None:
        from app.models.group import GroupMember

        result = await self.db.execute(
            select(GroupMember.role).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
        )
        role = result.scalar_one_or_none()
        if role not in {"owner", "editor"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to edit this group draft",
            )

    async def _require_group_member(self, group_id: str, user_id: str) -> None:
        from app.models.group import GroupMember

        result = await self.db.execute(
            select(GroupMember.id).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to access this group draft",
            )

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _require_authoring(self, user_id: str) -> None:
        service = SkillService(self.db)
        await service._require_tenant_skill_authoring(user_id)

    async def _resolve_ai_config(self, conversation: Conversation):
        from app.models.ai_config import AIConfig
        from app.services.llm_credentials import (
            ensure_ai_config_api_key,
            ensure_ai_config_endpoint_allowed,
            get_platform_default_ai_config,
            is_ai_config_ready,
        )

        ai_config = None
        if conversation.customer_id:
            ch = await self.db.get(CustomerConfig, conversation.customer_id)
            if ch and ch.ai_config_id:
                ai_config = await self.db.get(AIConfig, ch.ai_config_id)
        if ai_config is None and conversation.ai_config_id:
            ai_config = await self.db.get(AIConfig, conversation.ai_config_id)
        if ai_config is None:
            ai_config = await get_platform_default_ai_config(self.db)
        if ai_config is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No AI configuration available for skill drafting",
            )
        ai_config = await ensure_ai_config_api_key(self.db, ai_config)
        await ensure_ai_config_endpoint_allowed(self.db, ai_config)
        if not is_ai_config_ready(ai_config.provider, ai_config.api_key):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI API key not configured for skill drafting",
            )
        return ai_config

    async def _conversation_accessible(
        self, conversation: Conversation, user_id: str, *, is_admin: bool
    ) -> bool:
        """Same rules as chat: owner, visitor, channel tenant, or admin."""
        if is_admin:
            return True
        if conversation.user_id in (None, user_id):
            return True
        if conversation.customer_id:
            channel = await self.db.get(CustomerConfig, conversation.customer_id)
            if channel is not None and channel.user_id == user_id:
                return True
        return False

    async def _assert_conversation_access(
        self, conversation_id: str, user_id: str, *, is_admin: bool
    ) -> Conversation:
        conversation = await self.db.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        if not await self._conversation_accessible(conversation, user_id, is_admin=is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to access this conversation",
            )
        return conversation

    async def _load_transcript(self, conversation_id: str, *, limit: int = 40) -> str:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(limit)
        )
        rows = result.scalars().all()
        lines: list[str] = []
        for msg in rows:
            role = msg.role or "user"
            content = (msg.content or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines) if lines else "(empty conversation)"

    @staticmethod
    def _normalize_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
        name = SkillService._safe_folder_name(str(payload.get("name") or "skill"))
        description = str(payload.get("description") or "").strip() or None
        skill_type = str(payload.get("skill_type") or "tool").strip().lower()
        if skill_type not in {"tool", "function", "webhook"}:
            skill_type = "tool"

        files_raw = payload.get("files")
        files: dict[str, str] = {}
        if isinstance(files_raw, dict):
            for path, content in files_raw.items():
                safe = _safe_relative_path(str(path))
                if safe and isinstance(content, str):
                    files[safe] = content
        elif isinstance(files_raw, list):
            for item in files_raw:
                if not isinstance(item, dict):
                    continue
                safe = _safe_relative_path(str(item.get("path") or ""))
                content = item.get("content")
                if safe and isinstance(content, str):
                    files[safe] = content

        if "SKILL.md" not in files:
            desc_line = description or name
            files["SKILL.md"] = (
                f"---\nname: {name}\ndescription: \"{desc_line}\"\n"
                f"type: {skill_type}\n---\n\n# {name}\n\n{desc_line}\n"
            )

        return {
            "name": name,
            "description": description,
            "skill_type": skill_type,
            "files": files,
        }

    def _write_draft_files(self, user_id: str, draft_id: str, files: dict[str, str], *, group_id: str | None = None) -> None:
        base = _files_dir(user_id, draft_id, group_id)
        if base.exists():
            for child in base.iterdir():
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    import shutil

                    shutil.rmtree(child)
        base.mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def _read_draft_files(self, user_id: str, draft_id: str, *, group_id: str | None = None) -> list[SkillDraftFileEntry]:
        base = _files_dir(user_id, draft_id, group_id)
        if not base.exists():
            return []
        entries: list[SkillDraftFileEntry] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(base).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            entries.append(SkillDraftFileEntry(path=rel, content=text))
        return entries

    def _load_manifest(self, user_id: str, draft_id: str, *, group_id: str | None = None) -> dict[str, Any]:
        path = _manifest_path(user_id, draft_id, group_id)
        if not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found",
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        if group_id:
            if data.get("group_id") != group_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        elif data.get("user_id") != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return data

    def _save_manifest(self, user_id: str, draft_id: str, data: dict[str, Any], *, group_id: str | None = None) -> None:
        path = _manifest_path(user_id, draft_id, group_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _mark_conversation_draft_committed(
        self,
        *,
        conversation_id: str | None,
        draft_id: str,
        skill_id: str,
        skill_name: str,
    ) -> None:
        if not conversation_id:
            return

        result = await self.db.execute(
            select(Message).where(Message.conversation_id == conversation_id)
        )
        messages = result.scalars().all()
        for message in messages:
            extra = message.extra_data or {}
            skill_draft = extra.get("skill_draft") if isinstance(extra, dict) else None
            if not isinstance(skill_draft, dict):
                continue
            if str(skill_draft.get("draft_id") or "") != draft_id:
                continue

            updated_skill_draft = dict(skill_draft)
            updated_skill_draft["status"] = "committed"
            updated_skill_draft["saved_skill"] = {
                "id": skill_id,
                "name": skill_name,
            }
            updated_extra = dict(extra)
            updated_extra["skill_draft"] = updated_skill_draft
            message.extra_data = updated_extra

        await self.db.flush()

    def _to_response(self, data: dict[str, Any], user_id: str) -> SkillDraftResponse:
        draft_id = str(data["id"])
        files = self._read_draft_files(user_id, draft_id, group_id=data.get("group_id"))
        return SkillDraftResponse(
            id=draft_id,
            conversation_id=data.get("conversation_id"),
            group_id=data.get("group_id"),
            name=data.get("name") or "skill",
            description=data.get("description"),
            skill_type=data.get("skill_type") or "tool",
            files=files,
            status=data.get("status") or "draft",
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    async def list_drafts(self, user_id: str, *, group_id: str | None = None) -> list[SkillDraftResponse]:
        if group_id:
            await self._require_group_member(group_id, user_id)
            root = _group_drafts_root(group_id)
        else:
            await self._require_authoring(user_id)
            root = _drafts_root(user_id)
        items: list[SkillDraftResponse] = []
        if not root.exists():
            return items
        for child in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
            if not child.is_dir():
                continue
            manifest = child / "manifest.json"
            if not manifest.is_file():
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if data.get("status") == "committed":
                    continue
                if group_id and data.get("group_id") != group_id:
                    continue
                items.append(self._to_response(data, user_id))
            except Exception as e:
                logger.warning(f"Skip invalid draft {child.name}: {e}")
        return items

    async def get_draft(self, user_id: str, draft_id: str, *, group_id: str | None = None) -> SkillDraftResponse:
        if group_id:
            await self._require_group_member(group_id, user_id)
        else:
            await self._require_authoring(user_id)
        data = self._load_manifest(user_id, draft_id, group_id=group_id)
        return self._to_response(data, user_id)

    async def create_from_chat(
        self,
        *,
        user_id: str,
        conversation_id: str,
        hint: str | None = None,
        is_admin: bool = False,
        existing_draft_id: str | None = None,
    ) -> SkillDraftResponse:
        await self._require_authoring(user_id)
        conversation = await self._assert_conversation_access(
            conversation_id, user_id, is_admin=is_admin
        )
        group_id = conversation.scope_id if conversation.scope_type == "group" else None
        if group_id:
            await self._require_group_editor(group_id, user_id)
        transcript = await self._load_transcript(conversation_id)
        ai_config = await self._resolve_ai_config(conversation)

        user_prompt = f"Chat transcript:\n\n{transcript}\n"
        if hint and hint.strip():
            user_prompt += f"\nAuthor hint: {hint.strip()}\n"
        if existing_draft_id:
            try:
                prev = self._load_manifest(user_id, existing_draft_id, group_id=group_id)
                prev_files = self._read_draft_files(user_id, existing_draft_id, group_id=group_id)
                user_prompt += "\nRevise this existing draft:\n"
                user_prompt += json.dumps(
                    {
                        "name": prev.get("name"),
                        "description": prev.get("description"),
                        "files": {f.path: f.content for f in prev_files},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            except HTTPException:
                pass

        payload = await llm_complete_json(
            ai_config,
            system=_SKILL_DRAFT_SYSTEM,
            user=user_prompt,
        )
        normalized = self._normalize_llm_payload(payload)

        now = _utcnow().isoformat()
        draft_id = existing_draft_id or uuid.uuid4().hex
        created_at = now
        if existing_draft_id:
            try:
                prev_manifest = self._load_manifest(user_id, draft_id)
                created_at = prev_manifest.get("created_at", now)
            except HTTPException:
                pass
        manifest = {
            "id": draft_id,
            "user_id": user_id,
            "group_id": group_id,
            "conversation_id": conversation_id,
            "name": normalized["name"],
            "description": normalized["description"],
            "skill_type": normalized["skill_type"],
            "status": "draft",
            "created_at": created_at,
            "updated_at": now,
        }
        self._write_draft_files(user_id, draft_id, normalized["files"], group_id=group_id)
        self._save_manifest(user_id, draft_id, manifest, group_id=group_id)
        return self._to_response(manifest, user_id)

    async def update_draft(
        self,
        user_id: str,
        draft_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        skill_type: str | None = None,
        files: list[SkillDraftFileEntry] | None = None,
        group_id: str | None = None,
    ) -> SkillDraftResponse:
        if group_id:
            await self._require_group_editor(group_id, user_id)
        else:
            await self._require_authoring(user_id)
        data = self._load_manifest(user_id, draft_id, group_id=group_id)
        if name is not None:
            data["name"] = SkillService._safe_folder_name(name)
        if description is not None:
            data["description"] = description.strip() or None
        if skill_type is not None:
            data["skill_type"] = skill_type
        if files is not None:
            file_map = {}
            for entry in files:
                safe = _safe_relative_path(entry.path)
                if safe:
                    file_map[safe] = entry.content
            if file_map:
                self._write_draft_files(user_id, draft_id, file_map, group_id=group_id)
        data["updated_at"] = _utcnow().isoformat()
        self._save_manifest(user_id, draft_id, data, group_id=group_id)
        return self._to_response(data, user_id)

    async def delete_draft(self, user_id: str, draft_id: str, *, group_id: str | None = None) -> None:
        if group_id:
            await self._require_group_editor(group_id, user_id)
        else:
            await self._require_authoring(user_id)
        self._load_manifest(user_id, draft_id, group_id=group_id)
        import shutil

        draft_dir = (_group_drafts_root(group_id) if group_id else _drafts_root(user_id)) / draft_id
        if draft_dir.exists():
            shutil.rmtree(draft_dir)

    async def commit_draft(
        self,
        user_id: str,
        draft_id: str,
        *,
        customer_id: str | None = None,
        bind_channel: bool = True,
        group_id: str | None = None,
    ):
        from app.schemas.skill import SkillResponse

        if group_id:
            await self._require_group_editor(group_id, user_id)
        else:
            await self._require_authoring(user_id)
        data = self._load_manifest(user_id, draft_id, group_id=group_id)
        files = self._read_draft_files(user_id, draft_id, group_id=group_id)
        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Draft has no files",
            )

        skill_service = SkillService(self.db)
        skills_dir = _group_skills_root(group_id) if group_id else skill_service._skills_root(user_id)
        folder_name = SkillService._safe_folder_name(str(data.get("name") or "skill"))
        target_dir = skills_dir / folder_name
        if target_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Skill directory already exists: {folder_name}",
            )
        target_dir.mkdir(parents=True, exist_ok=True)
        for entry in files:
            safe = _safe_relative_path(entry.path)
            if not safe:
                continue
            out = target_dir / safe
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(entry.content, encoding="utf-8")

        from app.models.skill import Skill

        if group_id:
            conflict = await self.db.execute(
                select(Skill).where(
                    Skill.group_id == group_id,
                    Skill.name == folder_name,
                )
            )
            if conflict.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Group skill already exists: {folder_name}",
                )
            skill = Skill(
                user_id=user_id,
                group_id=group_id,
                name=folder_name,
                description=data.get("description"),
                skill_type=data.get("skill_type") or "tool",
                path=str((target_dir / "SKILL.md").resolve()),
                config={"origin": "group", "group_shared": True},
                enabled=True,
            )
            self.db.add(skill)
            await self.db.flush()
            await self.db.refresh(skill)
        else:
            await skill_service.reload_skills(user_id)
            result = await self.db.execute(
                select(Skill).where(
                    Skill.user_id == user_id,
                    Skill.name == folder_name,
                )
            )
            skill = result.scalar_one_or_none()
            if skill is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Skill committed on disk but not registered",
                )

        if bind_channel and customer_id and not group_id:
            channel = await self.db.get(CustomerConfig, customer_id)
            if channel is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Channel not found",
                )
            from app.middleware.auth import has_global_scope

            user = await self.db.get(User, user_id)
            is_admin = user is not None and await has_global_scope(user, self.db)
            if channel.user_id != user_id and not is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not allowed to bind skill to this channel",
                )
            current = [str(x) for x in (channel.skill_ids or []) if x]
            if skill.id not in current:
                current.append(skill.id)
                channel.skill_ids = await filter_tenant_skill_ids(
                    self.db, channel.user_id, current
                )
                await self.db.flush()

        data["status"] = "committed"
        data["updated_at"] = _utcnow().isoformat()
        self._save_manifest(user_id, draft_id, data, group_id=group_id)
        await self._mark_conversation_draft_committed(
            conversation_id=data.get("conversation_id"),
            draft_id=draft_id,
            skill_id=skill.id,
            skill_name=skill.name,
        )
        await skill_service._refresh_storage_usage(user_id)
        await self.db.commit()
        return SkillResponse.model_validate(skill)

    @staticmethod
    def parse_create_intent(content: str) -> str | None:
        """Return author hint for skill creation intents, else None.

        Supports explicit slash commands and narrow natural-language requests such as:
        - `/skill create csv to table`
        - `帮我建一个 skill，通过 json 数据 csv 转换成表格`
        - `create a skill that converts JSON/CSV into a table`
        """
        text = (content or "").strip()
        if not text:
            return None

        slash_patterns = (
            r"^/skill(?:\s+create)?(?:\s+(.*))?$",
            r"^/(?:做技能|保存技能)(?:\s+(.*))?$",
        )
        for pattern in slash_patterns:
            match = re.match(pattern, text, flags=re.IGNORECASE)
            if match:
                return (match.group(1) or "").strip() or None

        natural_patterns = (
            r"^(?:请)?(?:帮我|帮忙|给我)?(?:把|将)?(?:创建|新建|生成|做|建|制作|写|搞一个?)\s*(?:一个|个)?\s*(?:skill|技能)(?:[：:，,\s]+(.*))?$",
            r"^(?:请)?(?:帮我|帮忙|给我)?(?:把|将)?(?:这个|这段)?(?:对话|聊天)?(?:保存|整理|做成)\s*(?:为|成)?\s*(?:一个|个)?\s*(?:skill|技能)(?:[：:，,\s]+(.*))?$",
            r"^(?:please\s+)?(?:help\s+me\s+)?(?:create|make|build|generate|write)\s+(?:a|an)?\s*(?:skill|plugin|tool)(?:[\s:,-]+(.*))?$",
        )
        for pattern in natural_patterns:
            match = re.match(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            extracted = (match.group(1) or "").strip()
            return extracted or text
        return None

    @staticmethod
    def parse_slash_create(content: str) -> str | None:
        """Backward-compatible alias for older callers/tests."""
        return SkillDraftService.parse_create_intent(content)

    def draft_extra_data(self, draft: SkillDraftResponse) -> dict[str, Any]:
        preview = draft.files[0].content[:800] if draft.files else ""
        payload = {
            "type": "skill_draft",
            "draft_id": draft.id,
            "group_id": draft.group_id,
            "name": draft.name,
            "description": draft.description,
            "skill_type": draft.skill_type,
            "preview": preview,
            "file_count": len(draft.files),
        }
        if draft.status == "committed":
            payload["status"] = "committed"
        return payload
