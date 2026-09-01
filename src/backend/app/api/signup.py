"""Optional phone, username, and 9235 SSO signup routes."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.auth import TokenResponse
from app.schemas.signup import (
    PhoneSignupRequest,
    SendSmsRequest,
    SignupRequest,
    Sso9235CallbackRequest,
    SsoLoginUrlResponse,
)
from app.services import otp_service
from app.services.auth_service import AuthService
from app.services.patent9235_auth import (
    resolve_9235_login_url,
    sso_login_url,
    verify_xtk,
)

SignupRole = Literal["agent", "user"]


def create_signup_router(*, signup_role: SignupRole = "user") -> APIRouter:
    """Create public signup routes with an edition-specific new-user role."""
    router = APIRouter()

    @router.post("/signup", response_model=TokenResponse)
    async def signup(
        request: SignupRequest,
        db: AsyncSession = Depends(get_db),
    ) -> TokenResponse:
        """Register with username and password."""
        try:
            return await AuthService(db).signup(
                username=request.username,
                password=request.password,
                email=request.email,
                display_name=request.display_name,
                role=signup_role,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Signup failed: {exc}",
            ) from exc

    @router.post("/sms/send")
    async def send_sms_code(body: SendSmsRequest) -> dict[str, str]:
        """Send an SMS verification code for phone registration."""
        phone = otp_service.normalize_phone(body.phone)
        await otp_service.send_signup_otp(phone)
        return {"message": "ok"}

    @router.post("/signup/phone", response_model=TokenResponse)
    async def signup_by_phone(
        body: PhoneSignupRequest,
        db: AsyncSession = Depends(get_db),
    ) -> TokenResponse:
        """Register with a verified phone number."""
        phone = otp_service.normalize_phone(body.phone)
        await otp_service.verify_signup_otp(phone, body.code)
        try:
            return await AuthService(db).signup_by_phone(phone, role=signup_role)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Signup failed: {exc}",
            ) from exc

    @router.post("/login/phone", response_model=TokenResponse)
    async def login_by_phone(
        body: PhoneSignupRequest,
        db: AsyncSession = Depends(get_db),
    ) -> TokenResponse:
        """Sign in with a verified phone number."""
        phone = otp_service.normalize_phone(body.phone)
        await otp_service.verify_signup_otp(phone, body.code)
        try:
            return await AuthService(db).login_by_phone(phone)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Login failed: {exc}",
            ) from exc

    @router.get("/sso/9235/url", response_model=SsoLoginUrlResponse)
    async def sso_9235_url() -> SsoLoginUrlResponse:
        """Return the configured 9235 product-login URL."""
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
        """Exchange a browser redirect token for an MChat access token."""
        _ = channel
        claims = verify_xtk(xtk)
        return await AuthService(db).login_or_link_9235(
            account=claims["account"], role=signup_role
        )

    @router.post("/sso/9235/callback", response_model=TokenResponse)
    async def sso_9235_callback_post(
        body: Sso9235CallbackRequest,
        db: AsyncSession = Depends(get_db),
    ) -> TokenResponse:
        """Exchange an SPA callback token for an MChat access token."""
        claims = verify_xtk(body.xtk)
        return await AuthService(db).login_or_link_9235(
            account=claims["account"], role=signup_role
        )

    return router


# Compatibility export for Cloud and third-party imports. Core creates its own
# router below so that open registration lands in the Core agent experience.
router = create_signup_router()
