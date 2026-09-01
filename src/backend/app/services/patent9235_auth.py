"""Verify 9235.net SSO JWTs for optional Core and Cloud signup."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException, status
from jose import JWTError, jwt
from loguru import logger

from app.core.config import settings

PROVIDER = "patent9235"
_DEFAULT_9235_LOGIN_URL = "https://www.9235.net/user/login"
_PHONE_CN_RE = re.compile(r"^1[3-9]\d{9}$")


def normalize_9235_account(account: str) -> str:
    """Normalize a 9235 JWT subject (phone or email) for account linking."""
    value = (account or "").strip()
    if value.startswith("+86") and len(value) > 3:
        value = value[3:]
    if _PHONE_CN_RE.match(value):
        return value
    return (account or "").strip()


def resolve_9235_login_url() -> str:
    explicit = (settings.patent9235_sso_login_url or "").strip().rstrip("/")
    if explicit:
        return explicit
    base = (settings.patent9235_base_url or "").strip().rstrip("/")
    if base:
        return f"{base}/user/login"
    return _DEFAULT_9235_LOGIN_URL


def sso_login_url() -> str:
    """Build the 9235 product-login URL without a redirect_to parameter."""
    product_id = (
        (settings.patent9235_sso_product_id or "pdmchat").strip() or "pdmchat"
    )
    query = urlencode({"sso": "1", "productId": product_id})
    return f"{resolve_9235_login_url()}?{query}"


def mchat_callback_url(origin: str) -> str:
    return f"{origin.rstrip('/')}/auth/9235"


def verify_xtk(xtk: str) -> dict[str, Any]:
    """Verify a 9235 HS512 login token and return normalized claims."""
    secret = settings.patent9235_jwt_secret.strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="9235 SSO not configured (PATENT9235_JWT_SECRET)",
        )
    try:
        payload = jwt.decode(
            xtk,
            secret,
            algorithms=["HS512"],
            options={"verify_exp": True},
        )
    except JWTError as exc:
        logger.warning("9235 JWT verify failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid SSO token",
        ) from exc
    account = normalize_9235_account(str(payload.get("sub") or ""))
    if not account:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid SSO token subject",
        )
    return {
        "account": account,
        "unique_key": payload.get("uniqueKey"),
    }


async def fetch_9235_profile(account: str) -> dict[str, Any] | None:
    """Placeholder for a future 9235 profile introspection endpoint."""
    _ = account
    return None
