"""Chat service - business logic for conversations and messages."""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import event_bus
from app.models.ai_config import AIConfig
from app.models.conversation import Conversation
from app.models.group import Group, GroupMember
from app.models.message import Message
from app.models.user import User
from app.schemas.chat import (
    ConversationResponse,
    MessageResponse,
    ModelCapabilitiesResponse,
)
from app.services.llm_credentials import is_usable_api_key, resolve_api_key
from app.services.model_capabilities import model_capabilities
from app.utils.outbound_assets import enrich_message_extra_data


class ChatService:
    """Handles chat business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _is_group_member(self, user_id: str, group_id: str) -> bool:
        result = await self.db.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _actor_can_access_conversation(
        self,
        actor_user_id: str,
        conversation: Conversation,
    ) -> bool:
        if conversation.scope_type == "group" and conversation.scope_id:
            return await self._is_group_member(actor_user_id, conversation.scope_id)
        return conversation.user_id == actor_user_id

    async def _resolve_platform_ai_config(self) -> AIConfig | None:
        default_result = await self.db.execute(
            select(AIConfig).where(AIConfig.is_default == True)
        )
        cfg = default_result.scalar_one_or_none()
        if cfg is not None and is_usable_api_key(
            resolve_api_key(cfg.provider, cfg.api_key)
        ):
            return cfg
        all_result = await self.db.execute(select(AIConfig))
        for candidate in all_result.scalars().all():
            if is_usable_api_key(resolve_api_key(candidate.provider, candidate.api_key)):
                return candidate
        return None

    async def init_visitor_conversation(
        self,
        visitor_id: str | None = None,
        title: str | None = None,
        ai_config_id: str | None = None,
        contact_info: str | None = None,
        client_ip: str | None = None,
    ) -> ConversationResponse:
        """Initialize a conversation for a visitor (no auth)."""
        import uuid

        conversation = Conversation(
            id=str(uuid.uuid4()),
            visitor_id=visitor_id or f"visitor_{uuid.uuid4().hex[:8]}",
            ai_config_id=ai_config_id,
            title=title or "Visitor Chat",
            contact_info=contact_info,
            client_ip=client_ip,
            status="active",
        )
        self.db.add(conversation)
        await self.db.flush()
        await self.db.refresh(conversation)

        await event_bus.publish("conversation_created", conversation=conversation)

        return ConversationResponse.model_validate(conversation)

    async def send_message(
        self,
        conversation_id: str | None,
        content: str,
        role: str = "user",
        user: User | None = None,
        extra_data: dict | None = None,
    ) -> MessageResponse:
        """Send a message and trigger AI response processing."""
        normalized_extra_data = enrich_message_extra_data(content, extra_data)

        # Chat-driven skill authoring: slash command or natural-language intent.
        if role == "user" and user is not None and conversation_id:
            from app.middleware.auth import has_global_scope
            from app.services.skill_draft_service import SkillDraftService

            hint = SkillDraftService.parse_create_intent(content)
            if hint is not None:
                return await self._handle_skill_create_slash(
                    conversation_id=conversation_id,
                    content=content,
                    hint=hint,
                    user=user,
                    is_admin=await has_global_scope(user, self.db),
                )

        # Find or create conversation
        if conversation_id:
            result = await self.db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.status == "active",
                )
            )
            conversation = result.scalar_one_or_none()
            if conversation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Active conversation not found",
                )
            if conversation.customer_id and role == "user":
                from app.models.customer import CustomerConfig
                from app.services.subscription_gate import (
                    ensure_channel_subscription_active,
                )

                ch_result = await self.db.execute(
                    select(CustomerConfig).where(
                        CustomerConfig.id == conversation.customer_id
                    )
                )
                channel = ch_result.scalar_one_or_none()
                if channel is not None:
                    ensure_channel_subscription_active(channel)
        else:
            import uuid
            conversation = Conversation(
                id=str(uuid.uuid4()),
                user_id=user.id if user else None,
                title=content[:100] if content else "New Chat",
                status="active",
            )
            self.db.add(conversation)
            await self.db.flush()

        # Save user message
        message = Message(
            conversation_id=conversation.id,
            user_id=user.id if user else None,
            role=role,
            content=content,
            extra_data=normalized_extra_data,
        )
        self.db.add(message)
        await self.db.flush()

        # Update conversation timestamps
        conversation.updated_at = datetime.now(timezone.utc)
        conversation.last_seen_at = datetime.now(timezone.utc)

        # Commit BEFORE publishing event so the bot handler can see
        # this message and update the conversation without lock contention.
        await self.db.commit()

        # Increment usage only when conversation is bound to a specific channel
        if user is not None and role == "user":
            from app.models.customer import CustomerConfig

            customer_id = getattr(conversation, "customer_id", None)
            if customer_id:
                result = await self.db.execute(
                    select(CustomerConfig).where(
                        CustomerConfig.id == customer_id,
                        CustomerConfig.user_id == user.id,
                    )
                )
                config = result.scalar_one_or_none()
                if config is not None:
                    config.usage_messages_month = (
                        config.usage_messages_month or 0
                    ) + 1
                    await self.db.commit()

        # Only user messages should trigger the bot engine.
        if role == "user":
            await event_bus.publish(
                "message_created",
                message=message,
                conversation=conversation,
                user=user,
            )

        return MessageResponse.model_validate(message)

    async def _handle_skill_create_slash(
        self,
        *,
        conversation_id: str,
        content: str,
        hint: str | None,
        user: User,
        is_admin: bool,
    ) -> MessageResponse:
        """Handle `/skill create` without invoking the bot engine."""
        from app.services.skill_draft_service import SkillDraftService

        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.status == "active",
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active conversation not found",
            )

        draft_service = SkillDraftService(self.db)
        if not await draft_service._conversation_accessible(
            conversation, user.id, is_admin=is_admin
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed",
            )

        draft = await draft_service.create_from_chat(
            user_id=user.id,
            conversation_id=conversation_id,
            hint=hint,
            is_admin=is_admin,
        )
        draft_extra = draft_service.draft_extra_data(draft)

        user_msg = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            content=content,
            extra_data=None,
        )
        self.db.add(user_msg)

        assistant_msg = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            role="assistant",
            content=(
                f"已从对话生成技能草稿 **{draft.name}**，确认后保存到技能库。"
            ),
            extra_data={"skill_draft": draft_extra},
        )
        self.db.add(assistant_msg)
        conversation.updated_at = datetime.now(timezone.utc)
        conversation.last_seen_at = datetime.now(timezone.utc)
        await self.db.commit()
        return MessageResponse.model_validate(user_msg)

    async def list_conversations(
        self,
        user_id: str | None = None,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        search: str | None = None,
        customer_id: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> tuple[list[ConversationResponse], int]:
        """List conversations (optionally filtered by user)."""
        query = select(Conversation)
        count_query = select(func.count()).select_from(Conversation)

        if user_id:
            query = query.where(Conversation.user_id == user_id)
            count_query = count_query.where(Conversation.user_id == user_id)

        if customer_id:
            query = query.where(Conversation.customer_id == customer_id)
            count_query = count_query.where(Conversation.customer_id == customer_id)

        if scope_type:
            query = query.where(Conversation.scope_type == scope_type)
            count_query = count_query.where(Conversation.scope_type == scope_type)
        if scope_id is not None:
            query = query.where(Conversation.scope_id == scope_id)
            count_query = count_query.where(Conversation.scope_id == scope_id)

        if status:
            query = query.where(Conversation.status == status)
            count_query = count_query.where(Conversation.status == status)

        normalized_search = (search or "").strip()
        if normalized_search:
            search_filter = self._conversation_search_filter(normalized_search)
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        query = (
            query
            .order_by(Conversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(query)
        conversations = result.scalars().all()

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        counts = await self._message_counts_by_conversation(
            [c.id for c in conversations]
        )
        previews = await self._first_user_message_previews(
            [c.id for c in conversations]
        )

        # Batch-fetch usernames for display
        user_ids = list({c.user_id for c in conversations if c.user_id})
        usernames: dict[str, str] = {}
        if user_ids:
            user_result = await self.db.execute(
                select(User.id, User.username).where(User.id.in_(user_ids))
            )
            usernames = {row[0]: row[1] for row in user_result.all()}

        group_ids = list({c.scope_id for c in conversations if c.scope_type == "group" and c.scope_id})
        group_names: dict[str, str] = {}
        if group_ids:
            group_result = await self.db.execute(
                select(Group.id, Group.name).where(Group.id.in_(group_ids))
            )
            group_names = {row[0]: row[1] for row in group_result.all()}

        items: list[ConversationResponse] = []
        for conversation in conversations:
            items.append(
                await self._conversation_response_with_counts(
                    conversation, counts, previews, usernames, group_names
                )
            )
        return items, total

    def _conversation_search_filter(self, search: str):
        like = f"%{search}%"
        lowered = search.lower()

        filters: list[Any] = [
            Conversation.title.ilike(like),
            Conversation.visitor_id.ilike(like),
            Conversation.contact_info.ilike(like),
            Conversation.id.in_(
                select(Message.conversation_id).where(
                    Message.role == "user",
                    Message.content.ilike(like),
                )
            ),
        ]

        if lowered in {"widget", "网站", "网站widget", "website", "site"}:
            filters.append(
                or_(
                    Conversation.contact_info.ilike("widget_customer:%"),
                    Conversation.title.ilike("Widget:%"),
                )
            )
        if lowered in {"wechat", "微信", "公众号", "微信公众号"}:
            filters.append(Conversation.contact_info.ilike("wechat_channel:%"))
        if lowered in {"visitor", "访客"}:
            filters.append(Conversation.visitor_id.is_not(None))
        if lowered in {"admin", "后台"}:
            filters.append(Conversation.user_id.is_not(None))

        return or_(*filters)

    async def get_conversation_stats(
        self,
        user_id: str | None = None,
    ) -> dict[str, int]:
        """Return aggregate conversation counts."""
        base_query = select(func.count()).select_from(Conversation)

        total_query = base_query
        active_query = base_query.where(Conversation.status == "active")
        closed_query = base_query.where(Conversation.status == "closed")

        if user_id:
            total_query = total_query.where(Conversation.user_id == user_id)
            active_query = active_query.where(Conversation.user_id == user_id)
            closed_query = closed_query.where(Conversation.user_id == user_id)

        total = await self._count(total_query)
        active = await self._count(active_query)
        closed = await self._count(closed_query)

        return {
            "total": total,
            "active": active,
            "closed": closed,
        }

    async def _count(self, query) -> int:
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_conversation(
        self,
        conversation_id: str,
        user_id: str | None = None,
    ) -> ConversationResponse | None:
        """Get a conversation with its messages."""
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()

        if conversation is None:
            return None
        if user_id and not await self._actor_can_access_conversation(
            user_id, conversation
        ):
            return None
        counts = await self._message_counts_by_conversation([conversation.id])
        previews = await self._first_user_message_previews([conversation.id])
        group_names: dict[str, str] | None = None
        if conversation.scope_type == "group" and conversation.scope_id:
            group_result = await self.db.execute(
                select(Group.id, Group.name).where(Group.id == conversation.scope_id)
            )
            group_names = {row[0]: row[1] for row in group_result.all()}
        response = await self._conversation_response_with_counts(
            conversation, counts, previews, None, group_names
        )
        msg_result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        messages = [
            MessageResponse.model_validate(m) for m in msg_result.scalars().all()
        ]
        return response.model_copy(update={"messages": messages})

    async def _message_counts_by_conversation(
        self, conversation_ids: list[str]
    ) -> dict[str, dict[str, int]]:
        if not conversation_ids:
            return {}

        result = await self.db.execute(
            select(
                Message.conversation_id.label("conversation_id"),
                func.count(Message.id).label("total_count"),
                func.sum(
                    case((Message.role == "user", 1), else_=0)
                ).label("user_count"),
                func.sum(
                    case((Message.role == "assistant", 1), else_=0)
                ).label("ai_count"),
            )
            .where(Message.conversation_id.in_(conversation_ids))
            .group_by(Message.conversation_id)
        )

        counts: dict[str, dict[str, int]] = {}
        for row in result:
            counts[str(row.conversation_id)] = {
                "user": int(row.user_count or 0),
                "ai": int(row.ai_count or 0),
                "total": int(row.total_count or 0),
            }
        return counts

    async def _ai_capabilities_for_conversation(
        self, conversation: Conversation
    ) -> ModelCapabilitiesResponse | None:
        from app.models.ai_config import AIConfig
        from app.models.customer import CustomerConfig

        ai_config_id = conversation.ai_config_id
        if conversation.customer_id:
            channel_result = await self.db.execute(
                select(CustomerConfig).where(
                    CustomerConfig.id == conversation.customer_id
                )
            )
            channel = channel_result.scalar_one_or_none()
            if channel is not None and channel.ai_config_id:
                ai_config_id = channel.ai_config_id

        cfg = None
        if ai_config_id:
            cfg_result = await self.db.execute(
                select(AIConfig).where(AIConfig.id == ai_config_id)
            )
            cfg = cfg_result.scalar_one_or_none()
        if cfg is None:
            default_result = await self.db.execute(
                select(AIConfig).where(AIConfig.is_default == True)
            )
            cfg = default_result.scalar_one_or_none()

        if cfg is None:
            return None
        caps = model_capabilities(cfg.provider, cfg.model)
        return ModelCapabilitiesResponse(
            supports_attachments=caps.supports_attachments,
            supports_vision=caps.supports_vision,
        )

    async def _conversation_response_with_counts(
        self,
        conversation: Conversation,
        counts: dict[str, dict[str, int]],
        previews: dict[str, str],
        usernames: dict[str, str] | None = None,
        group_names: dict[str, str] | None = None,
    ) -> ConversationResponse:
        payload = ConversationResponse.model_validate(conversation).model_dump()
        metrics = counts.get(conversation.id, {"user": 0, "ai": 0, "total": 0})
        payload["user_message_count"] = metrics["user"]
        payload["ai_message_count"] = metrics["ai"]
        payload["total_message_count"] = metrics["total"]
        payload["conversation_type"] = self._conversation_type(conversation)
        payload["first_user_message_preview"] = previews.get(conversation.id)
        if conversation.user_id:
            payload["user_id"] = conversation.user_id
            if usernames:
                payload["username"] = usernames.get(conversation.user_id)
        if getattr(conversation, 'customer_id', None):
            payload["customer_id"] = getattr(conversation, 'customer_id', None)
        if conversation.scope_type == "group" and conversation.scope_id:
            payload["scope_name"] = (group_names or {}).get(conversation.scope_id)
        payload["ai_capabilities"] = await self._ai_capabilities_for_conversation(
            conversation
        )
        return ConversationResponse(**payload)

    async def _first_user_message_previews(
        self, conversation_ids: list[str]
    ) -> dict[str, str]:
        if not conversation_ids:
            return {}

        result = await self.db.execute(
            select(Message)
            .where(
                Message.conversation_id.in_(conversation_ids),
                Message.role == "user",
            )
            .order_by(Message.conversation_id.asc(), Message.created_at.asc())
        )

        previews: dict[str, str] = {}
        for message in result.scalars().all():
            conversation_id = str(message.conversation_id)
            if conversation_id in previews:
                continue
            previews[conversation_id] = self._message_preview(message)
        return previews

    def _message_preview(self, message: Message) -> str:
        content = (message.content or "").strip()
        extra_data = message.extra_data or {}
        attachments = extra_data.get("attachments") or []
        if attachments:
            attachment = attachments[0] if isinstance(attachments[0], dict) else {}
            name = str(attachment.get("name") or "").strip() or "attachment"
            mime = str(attachment.get("mime") or "").strip().lower()
            if mime.startswith("image/"):
                return content or f"[图片] {name}"
            if mime.startswith("video/"):
                return content or f"[视频] {name}"
            return content or f"[文件] {name}"
        return content or "-"

    def _conversation_type(self, conversation: Conversation) -> str:
        contact = (conversation.contact_info or "").strip().lower()
        title = (conversation.title or "").strip().lower()

        if contact.startswith("widget_customer:") or title.startswith("widget:"):
            return "widget"
        if contact.startswith("wechat_channel:"):
            return "wechat"
        if conversation.visitor_id:
            return "visitor"
        if conversation.user_id:
            return "admin"
        return "chat"

    async def create_conversation(
        self,
        user_id: str,
        title: str | None = None,
        ai_config_id: str | None = None,
        visitor_id: str | None = None,
        customer_id: str | None = None,
        scope_type: str = "personal",
        scope_id: str | None = None,
    ) -> ConversationResponse:
        """Create a new conversation for an authenticated user."""
        import uuid
        from app.models.customer import CustomerConfig
        from app.models.group import GroupMember

        resolved_customer_id = customer_id
        resolved_ai_config_id = ai_config_id
        if customer_id:
            result = await self.db.execute(
                select(CustomerConfig).where(
                    CustomerConfig.id == customer_id,
                    CustomerConfig.user_id == user_id,
                    CustomerConfig.enabled == True,
                )
            )
            channel = result.scalar_one_or_none()
            if channel is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Channel not found",
                )
            from app.services.subscription_gate import (
                ensure_channel_subscription_active,
            )

            ensure_channel_subscription_active(channel)
            resolved_ai_config_id = channel.ai_config_id or ai_config_id
        if scope_type == "group":
            if not scope_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="scope_id required for group scope",
                )
            membership_result = await self.db.execute(
                select(GroupMember).where(
                    GroupMember.group_id == scope_id,
                    GroupMember.user_id == user_id,
                )
            )
            if membership_result.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Group access denied",
                )

        conversation = Conversation(
            id=str(uuid.uuid4()),
            user_id=user_id,
            customer_id=resolved_customer_id,
            ai_config_id=resolved_ai_config_id,
            visitor_id=visitor_id,
            title=title or "New Chat",
            status="active",
            scope_type=scope_type,
            scope_id=scope_id,
        )
        self.db.add(conversation)
        await self.db.flush()
        await self.db.refresh(conversation)
        return ConversationResponse.model_validate(conversation)

    async def get_or_resume_channel_conversation(
        self,
        *,
        user_id: str,
        customer_id: str,
        title: str | None = None,
        force_new: bool = False,
        is_admin: bool = False,
        scope_type: str = "personal",
        scope_id: str | None = None,
    ) -> ConversationResponse:
        """Latest active conversation for a channel, or create one (studio chat home)."""
        from app.models.customer import CustomerConfig

        ch_query = select(CustomerConfig).where(
            CustomerConfig.id == customer_id,
            CustomerConfig.enabled == True,
        )
        if not is_admin:
            ch_query = ch_query.where(CustomerConfig.user_id == user_id)
        ch_result = await self.db.execute(ch_query)
        channel = ch_result.scalar_one_or_none()
        if channel is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Channel not found",
            )

        owner_id = channel.user_id
        resolved_title = title or channel.name or "New Chat"

        if force_new:
            active_result = await self.db.execute(
                select(Conversation).where(
                    Conversation.user_id == owner_id,
                    Conversation.customer_id == customer_id,
                    Conversation.scope_type == scope_type,
                    Conversation.scope_id == scope_id,
                    Conversation.status == "active",
                )
            )
            for conv in active_result.scalars().all():
                conv.status = "closed"
                conv.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            from app.bot import chat_extensions

            chat_extensions.on_force_new_conversation(owner_id, customer_id)
        else:
            result = await self.db.execute(
                select(Conversation)
                .where(
                    Conversation.user_id == owner_id,
                    Conversation.customer_id == customer_id,
                    Conversation.scope_type == scope_type,
                    Conversation.scope_id == scope_id,
                    Conversation.status == "active",
                )
                .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
                .limit(1)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                loaded = await self.get_conversation(
                    existing.id,
                    user_id=None if is_admin else owner_id,
                )
                if loaded is not None:
                    return loaded

        return await self.create_conversation(
            user_id=owner_id,
            title=resolved_title,
            customer_id=customer_id,
            scope_type=scope_type,
            scope_id=scope_id,
        )

    async def get_or_resume_group_conversation(
        self,
        *,
        user_id: str,
        group_id: str,
        title: str | None = None,
        force_new: bool = False,
    ) -> ConversationResponse:
        """Resume a group-scoped chat for a member (no personal assistant required)."""
        import uuid

        if not await self._is_group_member(user_id, group_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Group access denied",
            )

        group_result = await self.db.execute(select(Group).where(Group.id == group_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        ai_config = await self._resolve_platform_ai_config()
        if ai_config is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No platform AI configuration available",
            )

        resolved_title = title or group.name or "Group Chat"

        if force_new:
            active_result = await self.db.execute(
                select(Conversation).where(
                    Conversation.user_id == user_id,
                    Conversation.scope_type == "group",
                    Conversation.scope_id == group_id,
                    Conversation.status == "active",
                )
            )
            for conv in active_result.scalars().all():
                conv.status = "closed"
                conv.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
        else:
            result = await self.db.execute(
                select(Conversation)
                .where(
                    Conversation.user_id == user_id,
                    Conversation.scope_type == "group",
                    Conversation.scope_id == group_id,
                    Conversation.status == "active",
                )
                .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
                .limit(1)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                loaded = await self.get_conversation(existing.id, user_id=user_id)
                if loaded is not None:
                    return loaded

        conversation = Conversation(
            id=str(uuid.uuid4()),
            user_id=user_id,
            ai_config_id=ai_config.id,
            title=resolved_title,
            status="active",
            scope_type="group",
            scope_id=group_id,
        )
        self.db.add(conversation)
        await self.db.flush()
        await self.db.refresh(conversation)
        return ConversationResponse.model_validate(conversation)

    async def close_conversation(
        self,
        conversation_id: str,
        user_id: str | None = None,
    ) -> bool:
        """Close a conversation."""
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()

        if conversation is None:
            return False
        if user_id and not await self._actor_can_access_conversation(
            user_id, conversation
        ):
            return False

        conversation.status = "closed"
        conversation.updated_at = datetime.now(timezone.utc)

        await event_bus.publish(
            "conversation_closed", conversation=conversation
        )

        return True

    async def delete_conversation(
        self,
        conversation_id: str,
        actor_user_id: str,
    ) -> bool:
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            return False
        if not await self._actor_can_access_conversation(actor_user_id, conversation):
            raise HTTPException(status_code=403, detail="Cannot delete this conversation")

        await self.db.execute(
            Message.__table__.delete().where(Message.conversation_id == conversation_id)
        )
        await self.db.delete(conversation)
        await self.db.flush()
        return True
