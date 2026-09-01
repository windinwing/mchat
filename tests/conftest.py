"""Test configuration and fixtures."""

import asyncio
import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

# Ensure project root is on sys.path so tests.* imports work
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Also ensure backend src is importable
_backend_src = _project_root / "src" / "backend"
if str(_backend_src) not in sys.path:
    sys.path.insert(0, str(_backend_src))

# Use in-memory SQLite for tests — must be set BEFORE app imports so the
# application-level engine (database.py) also uses SQLite instead of MySQL.
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base, get_db
from app.core.config import settings as app_settings
from app.application import create_app

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    connect_args={"check_same_thread": False},
)
TestSessionFactory = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Create a single event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create tables before each test and drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session."""
    async with TestSessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP test client."""
    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_token(db_session: AsyncSession) -> str:
    """JWT for the default admin user (role=admin, full permissions)."""
    from sqlalchemy import select

    from app.core.security import create_access_token
    from app.models.user import User
    from app.services.auth_service import AuthService

    auth = AuthService(db_session)
    await auth.create_default_admin("admin", "admin123")
    await db_session.flush()
    result = await db_session.execute(select(User).where(User.username == "admin"))
    user = result.scalar_one()
    return create_access_token(
        data={"sub": user.id, "username": user.username, "role": user.role}
    )


@pytest_asyncio.fixture
async def auth_headers(admin_token: str) -> dict[str, str]:
    """Return authorization headers."""
    return {"Authorization": f"Bearer {admin_token}"}
