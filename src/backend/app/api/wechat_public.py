"""Public WeChat helpers for H5 mini program jump page."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.miniprogram_link_service import (
    parse_weixin_business_scheme,
    resolve_miniprogram_click_url,
)
from app.services.wechat_jssdk_service import build_jssdk_config

router = APIRouter()


@router.get("/jssdk-config")
async def wechat_jssdk_config(
    url: str = Query(..., min_length=8),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """JS-SDK signature for wx-open-launch-weapp on /mini-program."""
    try:
        return await build_jssdk_config(db, url)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e


@router.get("/miniprogram-resolve")
async def miniprogram_resolve(
    scheme: str = Query(..., min_length=12),
) -> dict:
    """Resolve weixin:// scheme to URL Link or HTTPS bridge."""
    parsed = parse_weixin_business_scheme(scheme)
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid weixin business scheme",
        )
    resolved = await resolve_miniprogram_click_url(scheme)
    return {
        "parsed": parsed,
        "click_url": resolved,
        "is_url_link": resolved.startswith("https://wxaurl.cn/")
        or resolved.startswith("https://wxurl.cn/"),
    }
