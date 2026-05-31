"""Chat service - business logic for conversations and messages."""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import event_bus
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.chat import (
    ConversationResponse,
    MessageResponse,
    ModelCapabilitiesResponse,
)
from app.services.model_capabilities import model_capabilities
from app.utils.outbound_assets import enrich_message_extra_data


class ChatService:
    """Handles chat business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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

    async def list_conversations(
        self,
        user_id: str | None = None,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        search: str | None = None,
        customer_id: str | None = None,
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

        items: list[ConversationResponse] = []
        for conversation in conversations:
            items.append(
                await self._conversation_response_with_counts(
                    conversation, counts, previews, usernames
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
        query = select(Conversation).where(
            Conversation.id == conversation_id
        )
        if user_id:
            query = query.where(Conversation.user_id == user_id)

        result = await self.db.execute(query)
        conversation = result.scalar_one_or_none()

        if conversation is None:
            return None
        counts = await self._message_counts_by_conversation([conversation.id])
        previews = await self._first_user_message_previews([conversation.id])
        response = await self._conversation_response_with_counts(
            conversation, counts, previews
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
    ) -> ConversationResponse:
        """Create a new conversation for an authenticated user."""
        import uuid
        from app.models.customer import CustomerConfig

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

        conversation = Conversation(
            id=str(uuid.uuid4()),
            user_id=user_id,
            customer_id=resolved_customer_id,
            ai_config_id=resolved_ai_config_id,
            visitor_id=visitor_id,
            title=title or "New Chat",
            status="active",
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
        query = select(Conversation).where(
            Conversation.id == conversation_id
        )
        if user_id:
            query = query.where(Conversation.user_id == user_id)

        result = await self.db.execute(query)
        conversation = result.scalar_one_or_none()

        if conversation is None:
            return False

        conversation.status = "closed"
        conversation.updated_at = datetime.now(timezone.utc)

        await event_bus.publish(
            "conversation_closed", conversation=conversation
        )

        return True
