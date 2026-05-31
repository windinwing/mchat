"""Load optional SMS providers from mchat-notify skill directory (not bundled in Core)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.skills_paths import iter_skills_roots
from app.services.sms.base import SmsSendResult
from app.services.sms.dev import DevSmsProvider


def _load_provider_module(name: str) -> Any | None:
    safe = (name or "").strip().lower()
    if not safe or safe == "dev":
        return None
    for root in iter_skills_roots():
        skill_dir = root / "mchat-notify" / "providers"
        mod_path = skill_dir / f"{safe}.py"
        if not mod_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location(
            f"mchat_notify_provider_{safe}", mod_path
        )
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        logger.debug("Loaded notify provider {} from {}", safe, mod_path)
        return mod
    return None


def get_sms_provider(name: str | None) -> Any:
    """Return dev provider or an optional plugin from skills/mchat-notify/providers/."""
    choice = (name or "dev").strip().lower()
    if choice in ("", "dev"):
        return DevSmsProvider()
    if choice == "auto":
        for candidate in ("smsbao", "aliyun", "custom"):
            mod = _load_provider_module(candidate)
            if mod is not None and hasattr(mod, "Provider"):
                return mod.Provider()
        return DevSmsProvider()

    mod = _load_provider_module(choice)
    if mod is not None and hasattr(mod, "Provider"):
        return mod.Provider()

    return _MissingProvider(choice)


class _MissingProvider:
    """Placeholder when a vendor provider file is not installed."""

    def __init__(self, name: str) -> None:
        self.name = name

    def send_text(self, phone: str, content: str) -> SmsSendResult:
        return SmsSendResult(
            ok=False,
            provider=self.name,
            message=(
                f"未安装短信 provider「{self.name}」。"
                f"请将 docs/examples/notify-providers/{self.name}.py.example "
                f"复制到 skills/mchat-notify/providers/{self.name}.py（勿提交公有仓库）。"
            ),
            provider_code="not_installed",
        )

    def send_template(
        self,
        phone: str,
        *,
        template_code: str,
        template_params: dict,
    ) -> SmsSendResult:
        return self.send_text(
            phone,
            f"[template:{template_code}] {template_params}",
        )
