"""MChat Cloud — Multi-tenant SaaS application.

Bootstraps the Core app and adds Cloud-specific routes.
Run with: uvicorn cloud.main:app
"""

from fastapi import FastAPI

from app.main import create_app as create_core_app
from cloud.api.auth import router as cloud_auth_router
from cloud.api.pay_callbacks import router as pay_callbacks_router
from cloud.api.payments import router as payments_router
from cloud.api.portal import router as portal_router
from cloud.api.templates import router as templates_router
from cloud.api.admin_templates import router as admin_templates_router
from cloud.api.admin_orders import router as admin_orders_router
from cloud.bot.studio_memory import register_cloud_chat_extensions

register_cloud_chat_extensions()

from app.bot.skill_draft_extensions import register_skill_draft_extensions

register_skill_draft_extensions()


def create_app() -> FastAPI:
    """Create the Cloud FastAPI application (Core + Cloud routes)."""
    app = create_core_app()

    # Cloud-specific routes
    app.include_router(cloud_auth_router, prefix="/api/auth", tags=["Auth"])
    app.include_router(pay_callbacks_router, prefix="/api/pay", tags=["Pay"])
    app.include_router(payments_router, prefix="/api/portal", tags=["Portal Payments"])
    app.include_router(portal_router, prefix="/api/portal", tags=["Portal"])
    app.include_router(templates_router, prefix="/api/templates", tags=["Templates"])
    app.include_router(admin_templates_router, prefix="/api", tags=["Admin Templates"])
    app.include_router(admin_orders_router, prefix="/api", tags=["Admin Orders"])

    # Seed channel templates on startup
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager
    from app.core.database import async_session_factory
    from app.models.channel_template import ChannelTemplate
    from sqlalchemy import select
    from loguru import logger

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def cloud_lifespan(inner_app: FastAPI) -> AsyncIterator[None]:
        async with original_lifespan(inner_app):
            async with async_session_factory() as db:
                existing = await db.execute(
                    select(ChannelTemplate).where(
                        ChannelTemplate.category == "patent_rag"
                    )
                )
                if existing.scalars().first() is None:
                    patent_template = ChannelTemplate(
                        name="专利查新助手",
                        description=(
                            "AI 驱动的专利检索与分析。上传专利文档或输入技术方案，"
                            "即可获取专利检索、权利要求分析、现有技术对比与查新报告。"
                        ),
                        category="patent_rag",
                        icon="FileSearch",
                        price_monthly_cents=2900,
                        price_yearly_cents=29000,
                        trial_days=14,
                        is_published=True,
                        sort_order=1,
                        default_ai_config_spec={
                            "provider": "openai",
                            "model": "gpt-4o-mini",
                            "system_prompt": (
                                "你是专利分析助手，帮助用户检索、分析和理解专利文档。"
                                "提供清晰的权利要求解释、现有技术对比和技术细节分析。"
                            ),
                        },
                        default_knowledge_base_spec={
                            "name": "专利知识库",
                            "chunk_strategy": "fixed",
                            "chunk_size": 1000,
                            "chunk_overlap": 100,
                            "embedding_provider": "ollama",
                            "embedding_model": "nomic-embed-text",
                            "embedding_dimension": 768,
                        },
                        default_theme={
                            "primaryColor": "#0891b2",
                            "botName": "专利助手",
                            "widgetTitle": "专利查新",
                        },
                        default_welcome_message=(
                            "你好！我是专利查新助手。请描述你的技术方案，"
                            "我将为你检索相关专利并提供分析。"
                        ),
                        default_offline_message="专利助手当前不在线，请留言。",
                    )
                    db.add(patent_template)

                    cs_template = ChannelTemplate(
                        name="AI 智能客服 (基础版)",
                        description=(
                            "基础 AI 客服通道，支持网站嵌入、知识库问答、"
                            "多渠道接入。适合需要标准客服功能的网站。"
                        ),
                        category="customer_service",
                        icon="MessageSquare",
                        price_monthly_cents=0,
                        price_yearly_cents=0,
                        trial_days=0,
                        is_published=True,
                        sort_order=0,
                        default_ai_config_spec={
                            "provider": "openai",
                            "model": "gpt-4o-mini",
                            "system_prompt": "你是一个专业的客服助手，请礼貌、准确地回答用户问题。",
                        },
                        default_theme={
                            "primaryColor": "#3b82f6",
                            "botName": "智能助手",
                            "widgetTitle": "在线客服",
                        },
                        default_welcome_message="你好！有什么可以帮助你的？",
                        default_offline_message="当前无客服在线，请留言。",
                    )
                    db.add(cs_template)
                    await db.commit()
                    logger.info("Seeded default channel templates")
            yield

    app.router.lifespan_context = cloud_lifespan
    return app


app = create_app()
