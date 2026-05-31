"""Development SMS provider — log only, no external call."""

from __future__ import annotations

from loguru import logger

from app.services.sms.base import SmsSendResult


class DevSmsProvider:
    name = "dev"

    def send_text(self, phone: str, content: str) -> SmsSendResult:
        logger.info("[dev-sms] to={} content={}", phone, content[:200])
        return SmsSendResult(
            ok=True,
            provider=self.name,
            message=f"dev mode: logged SMS to {phone}",
            provider_code="0",
        )

    def send_template(
        self,
        phone: str,
        *,
        template_code: str,
        template_params: dict,
    ) -> SmsSendResult:
        text = f"[template:{template_code}] {template_params}"
        return self.send_text(phone, text)
