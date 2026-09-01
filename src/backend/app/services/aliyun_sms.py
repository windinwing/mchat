"""Aliyun SMS API used by optional phone signup."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from loguru import logger

from app.core.config import settings

_API_URL = "https://dysmsapi.aliyuncs.com/"


def _special_url_encode(value: str) -> str:
    return (
        quote(value, safe="")
        .replace("+", "%20")
        .replace("*", "%2A")
        .replace("%7E", "~")
    )


def _sign(access_secret: str, string_to_sign: str) -> str:
    key = (access_secret + "&").encode("utf-8")
    digest = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def _build_signed_query(params: dict[str, str], access_key_secret: str) -> str:
    values = {key: value for key, value in params.items() if key != "Signature"}
    sorted_keys = sorted(values)
    sorted_query = "".join(
        f"&{_special_url_encode(key)}={_special_url_encode(values[key])}"
        for key in sorted_keys
    )
    string_to_sign = (
        "GET"
        + "&"
        + _special_url_encode("/")
        + "&"
        + _special_url_encode(sorted_query[1:])
    )
    signature = _special_url_encode(_sign(access_key_secret, string_to_sign))
    return f"Signature={signature}{sorted_query}"


def _gmt_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def send_verification_code(
    phone: str,
    code: str,
    *,
    out_id: str = "",
) -> None:
    """Send an OTP with the configured Aliyun SMS template."""
    access_id = settings.aliyun_sms_access_key_id.strip()
    access_key = settings.aliyun_sms_access_key_secret.strip()
    if not access_id or not access_key:
        raise RuntimeError("Aliyun SMS credentials not configured")

    params: dict[str, str] = {
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": str(uuid.uuid4()),
        "AccessKeyId": access_id,
        "SignatureVersion": "1.0",
        "Timestamp": _gmt_timestamp(),
        "Format": "JSON",
        "Action": "SendSms",
        "Version": "2017-05-25",
        "RegionId": settings.aliyun_sms_region,
        "PhoneNumbers": phone,
        "SignName": settings.aliyun_sms_sign_name,
        "TemplateCode": settings.aliyun_sms_template_code,
        "TemplateParam": json.dumps({"code": code}, ensure_ascii=False),
    }
    if out_id:
        params["OutId"] = out_id

    url = f"{_API_URL}?{_build_signed_query(params, access_key)}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    if data.get("Code", "") != "OK":
        message = data.get("Message", "Unknown error")
        logger.error(
            "Aliyun SMS failed phone={} code={} response={}",
            phone,
            code,
            data,
        )
        raise RuntimeError(message)

    logger.info(
        "Aliyun SMS sent phone={} RequestId={} BizId={}",
        phone,
        data.get("RequestId"),
        data.get("BizId"),
    )
