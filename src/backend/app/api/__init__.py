"""API routers package - includes all sub-routers under /api prefix."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.agent import router as agent_router
from app.api.knowledge import router as knowledge_router
from app.api.skill import router as skill_router
from app.api.skill_draft import router as skill_draft_router
from app.api.widget import router as widget_router
from app.api.health import router as health_router
from app.api.settings import router as settings_router
from app.api.channel import router as channel_router
from app.api.dashboard import router as dashboard_router
from app.api.speech import router as speech_router
from app.api.skill_schedule import router as skill_schedule_router
from app.api.workflow import router as workflow_router
from app.api.workspace import router as workspace_router
from app.api.wechat_public import router as wechat_public_router
from app.api.group import router as group_router
from app.api.gamecenter_bridge import router as gamecenter_bridge_router
from app.api.devbridge import router as devbridge_router
from app.api.devbridge_settings import router as devbridge_settings_router
from app.api.publish import router as publish_router

from app.core.config import settings

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
if settings.signup_enabled:
    try:
        from cloud.api.auth import router as cloud_auth_router

        api_router.include_router(cloud_auth_router, prefix="/auth", tags=["Auth"])
    except Exception:
        pass
api_router.include_router(chat_router, prefix="/chat", tags=["Chat"])
api_router.include_router(speech_router, prefix="/speech", tags=["Speech"])
api_router.include_router(agent_router, prefix="/agents", tags=["Agents"])
api_router.include_router(knowledge_router, prefix="/knowledge", tags=["Knowledge"])
api_router.include_router(skill_draft_router, prefix="/skills", tags=["Skill Drafts"])
api_router.include_router(skill_router, prefix="/skills", tags=["Skills"])
api_router.include_router(
    skill_schedule_router,
    prefix="/skills/schedules",
    tags=["Skill Schedules"],
)
api_router.include_router(workflow_router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(workspace_router, prefix="/workspace", tags=["Workspace"])
api_router.include_router(widget_router, prefix="/widget", tags=["Widget"])
api_router.include_router(settings_router, prefix="/settings", tags=["Settings"])
api_router.include_router(channel_router, prefix="/channels", tags=["Channels"])
api_router.include_router(group_router, prefix="/groups", tags=["Groups"])
api_router.include_router(devbridge_router, prefix="/devbridge", tags=["DevBridge"])
api_router.include_router(devbridge_settings_router, prefix="/devbridge/admin", tags=["DevBridge Settings"])
api_router.include_router(gamecenter_bridge_router, prefix="/gamecenter", tags=["GameCenter"])
api_router.include_router(publish_router, prefix="/publish", tags=["Publish"])
api_router.include_router(health_router, prefix="/health", tags=["Health"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(wechat_public_router, prefix="/wechat", tags=["WeChat"])

# Cloud admin APIs (templates, orders)
try:
    from cloud.api.admin_templates import router as admin_templates_router
    from cloud.api.admin_orders import router as admin_orders_router
    from cloud.api.admin_subscriptions import router as admin_subscriptions_router
    api_router.include_router(admin_templates_router)
    api_router.include_router(admin_orders_router)
    api_router.include_router(admin_subscriptions_router)
except Exception:
    pass
