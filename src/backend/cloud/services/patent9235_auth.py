"""Verify 9235.net SSO JWT and optional Redis share token."""

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
    """Normalize 9235 JWT subject (phone/email) for linking mchat users."""
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
    """
    Build 9235 login URL for product SSO (pdmchat → mchat).

    Do not pass redirect_to: 9235 UserController checks redirect_to before
    productId when the user is already logged in, and returns ?token= instead
    of the xtk JWT mchat expects.
    """
    base = resolve_9235_login_url()
    product_id = (settings.patent9235_sso_product_id or "pdmchat").strip() or "pdmchat"
    query = urlencode({"sso": "1", "productId": product_id})
    return f"{base}?{query}"


def mchat_callback_url(origin: str) -> str:
    return f"{origin.rstrip('/')}/auth/9235"


def verify_xtk(xtk: str) -> dict[str, Any]:
    """
    Verify JWT from 9235 product auth redirect (?xtk=...).
    Returns claims: account (phone/email), optional uniqueKey.
    """
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
    except JWTError as e:
        logger.warning("9235 JWT verify failed: {}", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid SSO token",
        ) from e
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
    """
    Optional: load user profile from 9235 (requires future introspection API).
    For now returns minimal dict from JWT account only.
    """
    _ = account
    return None
