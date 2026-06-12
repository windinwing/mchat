"""Cloud auth API — phone OTP signup and 9235.net SSO."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.auth import TokenResponse
from app.services.auth_service import AuthService
from cloud.schemas.auth import (
    PhoneSignupRequest,
    SendSmsRequest,
    SignupRequest,
    Sso9235CallbackRequest,
    SsoLoginUrlResponse,
)
from cloud.services import otp_service
from cloud.services.patent9235_auth import (
    resolve_9235_login_url,
    sso_login_url,
    verify_xtk,
)

router = APIRouter()


@router.post("/signup", response_model=TokenResponse)
async def signup(
    request: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Legacy username/password signup."""
    auth_service = AuthService(db)
    try:
        return await auth_service.signup(
            username=request.username,
            password=request.password,
            email=request.email,
            display_name=request.display_name,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Signup failed: {e}",
        ) from e


@router.post("/sms/send")
async def send_sms_code(body: SendSmsRequest) -> dict[str, str]:
    """Send SMS verification code for portal registration."""
    phone = otp_service.normalize_phone(body.phone)
    await otp_service.send_signup_otp(phone)
    return {"message": "ok"}


@router.post("/signup/phone", response_model=TokenResponse)
async def signup_by_phone(
    body: PhoneSignupRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register with phone + SMS code; email and nickname can be set later."""
    phone = otp_service.normalize_phone(body.phone)
    await otp_service.verify_signup_otp(phone, body.code)
    auth_service = AuthService(db)
    try:
        return await auth_service.signup_by_phone(phone)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Signup failed: {e}",
        ) from e


@router.post("/login/phone", response_model=TokenResponse)
async def login_by_phone(
    body: PhoneSignupRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Sign in with phone + SMS code (portal users)."""
    phone = otp_service.normalize_phone(body.phone)
    await otp_service.verify_signup_otp(phone, body.code)
    auth_service = AuthService(db)
    try:
        return await auth_service.login_by_phone(phone)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {e}",
        ) from e


@router.get("/sso/9235/url", response_model=SsoLoginUrlResponse)
async def sso_9235_url() -> SsoLoginUrlResponse:
    """URL to start 9235.net login (product SSO)."""
    if not (settings.patent9235_jwt_secret or "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="9235 SSO not configured (PATENT9235_JWT_SECRET)",
        )
    if not resolve_9235_login_url():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="9235 SSO login URL not configured",
        )
    return SsoLoginUrlResponse(url=sso_login_url())


@router.get("/sso/9235/callback", response_model=TokenResponse)
async def sso_9235_callback_get(
    xtk: str = Query(..., min_length=10),
    channel: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Browser redirect callback from 9235 (?xtk=...&channel=...)."""
    _ = channel
    claims = verify_xtk(xtk)
    auth_service = AuthService(db)
    return await auth_service.login_or_link_9235(account=claims["account"])


@router.post("/sso/9235/callback", response_model=TokenResponse)
async def sso_9235_callback_post(
    body: Sso9235CallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """SPA callback: exchange xtk for mchat JWT."""
    claims = verify_xtk(body.xtk)
    auth_service = AuthService(db)
    return await auth_service.login_or_link_9235(account=claims["account"])
