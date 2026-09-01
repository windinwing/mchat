"""Redis-backed SMS OTP service shared by Core and Cloud signup."""

import random
import re
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from loguru import logger

from app.core.config import settings

_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_REDIS: aioredis.Redis | None = None


def normalize_phone(raw: str) -> str:
    """Normalize a mainland China mobile number to 11 digits."""
    value = re.sub(r"\s+", "", raw or "")
    if value.startswith("+86"):
        value = value[3:]
    if value.startswith("86") and len(value) == 13:
        value = value[2:]
    if not _PHONE_RE.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number",
        )
    return value


async def _redis() -> aioredis.Redis:
    global _REDIS
    if _REDIS is None:
        _REDIS = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _REDIS


def _otp_key(phone: str) -> str:
    return f"mchat:otp:signup:{phone}"


def _cooldown_key(phone: str) -> str:
    return f"mchat:otp:cooldown:{phone}"


def _generate_code() -> str:
    if settings.sms_dev_mode:
        return settings.sms_dev_code
    return f"{random.randint(100000, 999999)}"


async def send_signup_otp(phone: str) -> None:
    """Store and send a signup OTP, enforcing the configured cooldown."""
    redis = await _redis()
    cooldown_key = _cooldown_key(phone)
    if await redis.exists(cooldown_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before requesting another code",
        )

    code = _generate_code()
    await redis.setex(_otp_key(phone), settings.otp_expire_seconds, code)
    await redis.setex(cooldown_key, settings.otp_send_cooldown_seconds, "1")

    if settings.sms_dev_mode:
        logger.info("SMS dev mode: OTP for {} is {}", phone, code)
        return

    from app.services.aliyun_sms import send_verification_code

    try:
        await send_verification_code(phone, code, out_id=f"mchat-signup-{phone}")
    except RuntimeError as exc:
        message = str(exc)
        logger.warning("Aliyun SMS error for {}: {}", phone, message)
        if "流控" in message or "Limit" in message or "BUSY" in message:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="SMS rate limit exceeded, try again later",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to send SMS",
        ) from exc
    except Exception as exc:
        logger.exception("Aliyun SMS unexpected error for {}", phone)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to send SMS",
        ) from exc


async def verify_signup_otp(phone: str, code: str) -> None:
    redis = await _redis()
    stored = await redis.get(_otp_key(phone))
    if not stored or stored != code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )
    await redis.delete(_otp_key(phone))


def phone_verified_now() -> datetime:
    return datetime.now(timezone.utc)
