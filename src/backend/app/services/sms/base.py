"""SMS provider protocol and shared helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol


_PHONE_RE = re.compile(r"^1\d{10}$")


def normalize_phone(raw: str) -> str:
    text = (raw or "").strip().replace(" ", "").replace("-", "")
    if text.startswith("+86"):
        text = text[3:]
    if text.startswith("86") and len(text) == 13:
        text = text[2:]
    return text


def is_valid_cn_mobile(phone: str) -> bool:
    return bool(_PHONE_RE.fullmatch(normalize_phone(phone)))


@dataclass
class SmsSendResult:
    ok: bool
    provider: str
    message: str
    provider_code: str = ""
    raw: dict[str, Any] | None = None


class SmsProvider(Protocol):
    name: str

    def send_text(self, phone: str, content: str) -> SmsSendResult: ...

    def send_template(
        self,
        phone: str,
        *,
        template_code: str,
        template_params: dict[str, Any],
    ) -> SmsSendResult: ...
