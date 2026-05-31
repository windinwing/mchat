"""Tests for SMS notification service."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.notification_service import NotificationService
from app.services.sms.base import normalize_phone


@pytest.fixture(autouse=True)
def _reset_sms_settings(monkeypatch):
    monkeypatch.setattr(settings, "sms_phone_allowlist", ["13800138000", "13900139000"])
    monkeypatch.setattr(settings, "sms_alert_phones", [])
    monkeypatch.setattr(settings, "sms_default_provider", "dev")
    monkeypatch.setattr(settings, "sms_send_cooldown_seconds", 60)
    monkeypatch.setattr(
        NotificationService,
        "check_rate_limit",
        lambda self, phone: True,
    )


def test_normalize_phone():
    assert normalize_phone("+86 138 0013 8000") == "13800138000"


def test_dev_send_requires_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "sms_phone_allowlist", [])
    svc = NotificationService()
    out = svc.send_sms(phone="13800138000", content="hi")
    assert out["ok"] is False
    assert out["error"] == "phone_not_allowed"


def test_dev_send_ok():
    svc = NotificationService()
    out = svc.send_sms(phone="13800138000", content="hello")
    assert out["ok"] is True
    assert out["provider"] == "dev"


def test_mchat_notify_skill_ping(monkeypatch):
    monkeypatch.setattr(settings, "sms_phone_allowlist", ["13900139000"])
    skill_dir = Path(__file__).resolve().parents[2] / "skills" / "mchat-notify"
    spec = importlib.util.spec_from_file_location("mchat_notify_main", skill_dir / "main.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mchat_notify_main"] = mod
    spec.loader.exec_module(mod)
    out = mod.run(command="ping", phone="13900139000", provider="dev")
    assert out["ok"] is True


def test_workflow_alert_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "sms_workflow_alert_enabled", False)
    monkeypatch.setattr(settings, "sms_alert_phones", ["13800138000"])
    svc = NotificationService()
    assert svc.send_workflow_alert_sms(
        event="failed",
        workflow_name="Test",
        run_id="run-1",
        message="boom",
    ) == []
