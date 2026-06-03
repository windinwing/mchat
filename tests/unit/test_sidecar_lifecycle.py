"""Tests for sidecar lifecycle meta and idle helpers."""

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.workspace.sidecar_lifecycle import (
    idle_minutes_since,
    image_matches_running,
    read_sidecar_meta,
    touch_sidecar_activity,
)


def test_touch_and_read_sidecar_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root_dir", str(tmp_path / "tenants"))
    touch_sidecar_activity("user-1", image="python:3.12-slim")
    meta = read_sidecar_meta("user-1")
    assert meta.get("user_id") == "user-1"
    assert meta.get("image") == "python:3.12-slim"
    assert meta.get("last_active_at")


def test_idle_minutes_since(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root_dir", str(tmp_path / "tenants"))
    path = tmp_path / "tenants" / "user-1" / "data" / ".mchat" / "sidecar.meta.json"
    path.parent.mkdir(parents=True)
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    path.write_text(f'{{"last_active_at": "{old}"}}', encoding="utf-8")
    assert idle_minutes_since("user-1") is not None
    assert idle_minutes_since("user-1") >= 29


def test_image_matches_running():
    assert image_matches_running("python:3.12-slim", "python:3.12-slim")
    assert image_matches_running("python:3.12-slim", "docker.io/library/python:3.12-slim")
