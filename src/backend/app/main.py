"""FastAPI application entry point."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.event_bus import event_bus
from app.exceptions import MChatError
from app.knowledge.milvus_client import milvus_client
from app.utils.logger import setup_logger
from app.utils.upload_paths import resolve_upload_root


def _validate_production_security() -> None:
    """Refuse to start in production with known-insecure defaults."""
    if (settings.environment or "development").strip().lower() != "production":
        return
    problems: list[str] = []
    if settings.jwt_secret == "change-this-to-a-random-secret-key":
        problems.append("JWT_SECRET must be set to a random value")
    if settings.admin_password == "admin123":
        problems.append("ADMIN_PASSWORD must not be the default admin123")
    if settings.show_bootstrap_credentials:
        problems.append("SHOW_BOOTSTRAP_CREDENTIALS must be false in production")
    if problems:
        raise RuntimeError(
            "Insecure production configuration: " + "; ".join(problems)
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown events."""
    # Startup
    logger.info("Starting mchat backend server...")

    _validate_production_security()

    if settings.jwt_secret == "change-this-to-a-random-secret-key":
        logger.warning(
            "⚠️  JWT_SECRET 为默认值，请在生产环境中修改为随机字符串！"
        )

    # Initialize database
    await init_db()

    # Create default admin user
    from app.core.database import async_session_factory
    from app.services.auth_service import AuthService
    async with async_session_factory() as db:
        auth_service = AuthService(db)
        await auth_service.create_default_admin(
            username=settings.admin_username,
            password=settings.admin_password,
        )
        await db.commit()

    # Auto-reload skills from filesystem for the primary admin user
    from app.services.skill_service import SkillService
    from app.models.user import User
    from sqlalchemy import select
    async with async_session_factory() as db:
        user_result = await db.execute(
            select(User).where(User.username == settings.admin_username)
        )
        primary_user = user_result.scalar_one_or_none()
        if primary_user is not None:
            skill_service = SkillService(db)
            await skill_service.reload_skills(user_id=primary_user.id)
        await db.commit()

    # Load Milvus settings from DB, then connect
    from app.services.settings_service import SettingsService

    async with async_session_factory() as db:
        await SettingsService(db).get_settings()
        await db.commit()
    if settings.storage_backend.strip().lower() == "local":
        os.makedirs(resolve_upload_root(), exist_ok=True)
    await milvus_client.connect()
    if milvus_client._connected:
        await milvus_client.create_collection()

    logger.info("mchat backend server started successfully")
    yield

    # Shutdown
    logger.info("Shutting down mchat backend server...")
    await close_db()
    await milvus_client.close()
    event_bus.clear()
    logger.info("mchat backend server stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # Ensure required directories exist
    storage_backend = (settings.storage_backend or "local").strip().lower()
    if storage_backend == "local":
        os.makedirs(resolve_upload_root(), exist_ok=True)
    os.makedirs(settings.skills_path, exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    # Setup logging
    setup_logger()

    app = FastAPI(
        title="MChat API",
        description=(
            "MChat — Multi-tenant vertical RAG platform. "
            "Features: streaming Bot engine with tool calling, "
            "RAG knowledge base (multi-strategy chunking, hybrid search, "
            "multi-provider rerank), Skill plugin system, embedded chat Widget, "
            "and multi-channel support (WeChat, Web Widget, REST, WebSocket). "
            "Ships with AI customer service as a built-in channel; extensible "
            "to patent search, medical, legal, and other vertical RAG channels."
        ),
        version="1.0.0",
        lifespan=lifespan,
        contact={
            "name": "MChat",
            "url": "https://github.com/windinwing/mchat",
        },
        license_info={
            "name": "MIT",
            "url": "https://github.com/windinwing/mchat/blob/main/LICENSE",
        },
        openapi_tags=[
            {"name": "Auth", "description": "Authentication, user management, JWT tokens"},
            {"name": "Chat", "description": "Conversations and messages (SSE streaming, file upload)"},
            {"name": "Agents", "description": "AI model configs and vertical channel configurations"},
            {"name": "Knowledge", "description": "Knowledge bases, documents, RAG search, embedding models"},
            {"name": "Skills", "description": "Skill plugin management — upload, install from URL, reload"},
            {
                "name": "Skill Schedules",
                "description": "Skill scheduled jobs — CRUD, run-once, execution logs",
            },
            {
                "name": "Workflows",
                "description": "Skill orchestration workflows — steps, run-once, execution logs",
            },
            {"name": "Widget", "description": "Public API for embedded chat widget (no auth)"},
            {"name": "Channels", "description": "Multi-channel configuration (WeChat, etc.)"},
            {"name": "Speech", "description": "Speech-to-text transcription"},
            {"name": "Settings", "description": "System settings, logs, Milvus test"},
            {"name": "Health", "description": "Health check and metrics"},
            {"name": "Dashboard", "description": "Dashboard stats and activity feed"},
        ],
    )

    # CORS middleware
    cors_origins_raw = settings.cors_origins.strip()
    if cors_origins_raw == "*":
        allow_origins = ["*"]
        allow_credentials = False
    else:
        allow_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
        allow_credentials = True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security headers middleware
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    from app.middleware.maintenance import register_maintenance_middleware

    register_maintenance_middleware(app)

    # Rate limiting (when enabled)
    if settings.rate_limit_enabled:
        from app.middleware.ratelimit import RateLimitMiddleware
        app.add_middleware(
            RateLimitMiddleware,
            rate=settings.rate_limit_requests,
            per_seconds=settings.rate_limit_period,
            path_limits={
                "/api/auth/login": (
                    settings.login_rate_limit,
                    settings.login_rate_limit_period,
                ),
                "/api/auth/register": (
                    settings.login_rate_limit,
                    settings.login_rate_limit_period,
                ),
            },
        )

    # Global exception handlers
    @app.exception_handler(MChatError)
    async def mchat_exception_handler(request: Request, exc: MChatError):
        logger.warning(
            "MChatError: {} (status={}) path={}",
            exc.message, exc.status_code, request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "error": type(exc).__name__},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        logger.warning(
            "RequestValidationError: {} errors path={}",
            len(errors), request.url.path,
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed",
                "errors": [
                    {"loc": e.get("loc", []), "msg": e.get("msg", "")}
                    for e in errors
                ],
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception on {} {}: {}",
            request.method, request.url.path, str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # Same-origin /uploads — proxies MinIO/S3 or serves local files
    from app.api.uploads import router as uploads_router

    app.include_router(uploads_router)

    # Include API routers
    from app.api import api_router
    app.include_router(api_router)

    # Include WebSocket router
    from app.websocket.route import router as ws_router
    app.include_router(ws_router)

    # Initialize bot engine (subscribes to message_created events)
    from app.bot.handler import init_bot_engine
    init_bot_engine()

    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "name": "mchat Backend",
            "version": "1.0.0",
            "docs": "/docs",
        }

    @app.get("/go/{short_code}")
    async def redirect_by_short_code(short_code: str, request: Request):
        """Redirect short code to widget page, e.g. /go/gdz → /widget.html?agentId=xxx"""
        from urllib.parse import urlencode
        from fastapi.responses import RedirectResponse, PlainTextResponse
        from sqlalchemy import select
        from app.core.database import async_session_factory
        from app.models.customer import CustomerConfig
        from app.services.widget_chat_service import ensure_widget_domain_allowed

        sw_code = short_code.strip().lower()
        async with async_session_factory() as db:
            result = await db.execute(
                select(CustomerConfig).where(
                    CustomerConfig.short_code == sw_code,
                    CustomerConfig.enabled == True,
                )
            )
            config = result.scalar_one_or_none()
            if config is None:
                return PlainTextResponse("Not Found", status_code=404)

            ensure_widget_domain_allowed(config, request)
            params = {"agentId": config.id}
            widget_url = f"/widget.html?{urlencode(params)}"
            return RedirectResponse(url=widget_url, status_code=302)

    return app


app = create_app()


def main() -> None:
    """Run the application with uvicorn."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
