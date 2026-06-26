"""Security utilities: password hashing and JWT tokens."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash (CPU-intensive, ~0.2-1.5s).

    NOTE: callers in async code should prefer ``verify_password_async`` so the
    bcrypt compute runs on a worker thread and does NOT block the event loop.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8") if isinstance(hashed_password, str) else hashed_password,
        )
    except (ValueError, TypeError):
        return False


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Async wrapper: run bcrypt on a worker thread so it doesn't block the loop.

    bcrypt.checkpw is CPU-bound and takes 0.2-1.5s. Calling it inline in an async
    endpoint freezes the entire event loop for that duration — every other
    request (chat, websocket) stalls. Running it via to_thread yields the loop
    so concurrency is preserved.
    """
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def verify_access_token(token: str) -> dict[str, Any]:
    """Verify and decode a JWT access token.

    Raises:
        JWTError: If token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        raise
