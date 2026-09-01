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
from app.knowledge.es_client import es_knowledge_client
from app.utils.logger import setup_logger
from app.utils.upload_paths import resolve_upload_root


def _validate_production_security() -> None:
    """Refuse to start in production with known-insecure defaults."""
    if (settings.environment or "development").strip().lower() != "production":
        return
    problems: list[str] = []
    jwt_secret = (settings.jwt_secret or "").strip()
    admin_password = (settings.admin_password or "").strip()
    database_url = (settings.database_url or "").strip()

    def _is_placeholder(value: str) -> bool:
        compact = value.lower().replace("-", "").replace("_", "").replace(" ", "")
        return any(
            marker in compact
            for marker in (
                "changeme",
                "changethis",
                "replaceme",
                "yoursecret",
                "example",
            )
        )

    if len(jwt_secret) < 32 or _is_placeholder(jwt_secret):
        problems.append(
            "JWT_SECRET must be at least 32 characters and not a placeholder"
        )
    if (
        len(admin_password) < 12
        or admin_password == "admin123"
        or _is_placeholder(admin_password)
    ):
        problems.append(
            "ADMIN_PASSWORD must be at least 12 characters and not a placeholder"
        )
    if settings.show_bootstrap_credentials:
        problems.append("SHOW_BOOTSTRAP_CREDENTIALS must be false in production")
    if _is_placeholder(database_url) or "mchat:mchat123@" in database_url.lower():
        problems.append("DATABASE_URL must not contain a placeholder password")
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

    # Start dedicated thread pool for skill execution (isolated from default pool
    # used by uploads/search/embeddings, so long-running skills don't starve them)
    from app.core.skills_pool import start_skills_pool
    start_skills_pool()

    # Create default admin user
    from app.core.database import async_session_factory
    from app.services.auth_service import AuthService
    from app.services.llm_credentials import clear_legacy_rental_copied_api_keys
    async with async_session_factory() as db:
        auth_service = AuthService(db)
        await auth_service.create_default_admin(
            username=settings.admin_username,
            password=settings.admin_password,
        )
        if (settings.environment or "development").strip().lower() == "production":
            rotated_admins = await auth_service.rotate_legacy_admin_passwords(
                settings.admin_password
            )
            if rotated_admins:
                logger.warning(
                    "Rotated insecure legacy bootstrap password for {} admin account(s)",
                    len(rotated_admins),
                )
            cleared_ai_configs = await clear_legacy_rental_copied_api_keys(db)
            if cleared_ai_configs:
                logger.warning(
                    "Removed copied platform credentials from {} legacy rental "
                    "AI config(s); rotate the affected provider keys",
                    len(cleared_ai_configs),
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
    await es_knowledge_client.connect()

    # Start the background knowledge index runner and re-queue any documents
    # left mid-index by a previous (crashed/restarted) process.
    try:
        from app.knowledge.index_runner import (
            recover_stale_indexing,
            start_index_runner,
        )
        start_index_runner()
        await recover_stale_indexing()
    except ImportError:
        logger.warning("app.knowledge.index_runner not available, skipping index runner")

    # NOTE: DevBridge build workers run as a separate process
    # (ops/scripts/gamecenter-build-worker.py), NOT inside the API server.
    # This avoids blocking API workers during long compilations.

    logger.info("mchat backend server started successfully")
    yield

    # Shutdown
    logger.info("Shutting down mchat backend server...")
    from app.core.skills_pool import stop_skills_pool
    stop_skills_pool()
    try:
        from app.knowledge.index_runner import stop_index_runner
        await stop_index_runner()
    except ImportError:
        pass
    await close_db()
    await milvus_client.close()
    await es_knowledge_client.close()
    event_bus.clear()
    logger.info("mchat backend server stopped")


def create_app(
    *,
    include_signup_routes: bool | None = None,
    signup_enabled: bool | None = None,
    cloud_mode: bool = False,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Core deployments may opt into the phone/9235 signup routes. Cloud mounts
    the same router itself, so it passes ``False`` to avoid duplicate
    method/path registrations while reporting its own public signup state.
    """
    if include_signup_routes is None:
        include_signup_routes = settings.signup_enabled
    if signup_enabled is None:
        signup_enabled = include_signup_routes

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
    # Edition flags belong to this app instance. Keeping them off the global
    # settings object lets Core and Cloud factories coexist in one process.
    app.state.mchat_signup_enabled = signup_enabled
    app.state.mchat_cloud_mode = cloud_mode

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

    # Same-origin /uploads — proxies MinIO/S3 or serves local files.
    # Also mounted under /api/uploads so it reaches the backend through edge
    # gateways that only whitelist /api/ (the bare /uploads/ path 404s there).
    from app.api.uploads import router as uploads_router

    app.include_router(uploads_router)
    app.include_router(uploads_router, prefix="/api")

    # Skill 生成物的对外静态访问（如 textbook-review 的 HTML 复习提纲）。
    # 无签名、公开可访问，便于在浏览器/手机直接打开分享。
    # nginx 加一条 location /skill_assets/ { proxy_pass http://backend:3001; } 即可对外。
    # 目录：UPLOAD_DIR/skill_assets/，skill 把生成物写到这里。
    try:
        from fastapi.staticfiles import StaticFiles
        from app.utils.upload_paths import resolve_upload_root as _resolve_assets_root
        _assets_dir = _resolve_assets_root() / "skill_assets"
        _assets_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/skill_assets", StaticFiles(directory=str(_assets_dir)), name="skill_assets")
        logger.info("Skill assets served at /skill_assets/ from {}", _assets_dir)
    except Exception as _e:
        logger.warning("Failed to mount /skill_assets: {}", _e)

    # Include API routers
    from app.api import api_router
    app.include_router(api_router)

    if include_signup_routes:
        from app.api.signup import create_signup_router

        app.include_router(
            create_signup_router(signup_role="agent"),
            prefix="/api/auth",
            tags=["Auth"],
        )

    # Include WebSocket router
    from app.websocket.route import router as ws_router
    app.include_router(ws_router)

    # Interactive container shell (admin-only) — reuses the /ws nginx upgrade.
    from app.workspace.exec_ws import router as exec_ws_router
    app.include_router(exec_ws_router)

    # Chat extension hooks (once per process; idempotent; Cloud studio hooks register earlier in cloud/main.py)
    from app.bot.skill_draft_extensions import register_skill_draft_extensions
    from app.bot.gamecenter_bridge_extensions import register_gamecenter_bridge_extensions

    register_skill_draft_extensions()
    register_gamecenter_bridge_extensions()

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
