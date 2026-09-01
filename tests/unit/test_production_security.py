"""Production startup security validation."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.auth import bootstrap_hint
from app.core.security import get_password_hash, verify_password
from app.application import _validate_production_security
from app.models.user import User
from app.services.auth_service import AuthService


def test_production_security_allows_development_defaults(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "jwt_secret", "change-this-to-a-random-secret-key")
    monkeypatch.setattr(settings, "admin_password", "admin123")
    monkeypatch.setattr(settings, "show_bootstrap_credentials", True)
    _validate_production_security()


def test_production_security_rejects_default_secrets(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_secret", "change-this-to-a-random-secret-key")
    monkeypatch.setattr(settings, "admin_password", "admin123")
    monkeypatch.setattr(settings, "show_bootstrap_credentials", True)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _validate_production_security()


def test_production_security_rejects_placeholder_database_password(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(
        settings,
        "jwt_secret",
        "a-secure-random-jwt-secret-that-is-long-enough",
    )
    monkeypatch.setattr(settings, "admin_password", "a-secure-admin-password")
    monkeypatch.setattr(settings, "show_bootstrap_credentials", False)
    monkeypatch.setattr(
        settings,
        "database_url",
        "mysql+aiomysql://mchat:mchat_password_change_me@mysql:3306/mchat",
    )

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        _validate_production_security()


@pytest.mark.parametrize(
    ("jwt_secret", "admin_password", "message"),
    [
        (
            "change-me-to-a-random-secret-key-at-least-32-chars",
            "a-secure-admin-password",
            "JWT_SECRET",
        ),
        (
            "a-secure-random-jwt-secret-that-is-long-enough",
            "admin_change_me",
            "ADMIN_PASSWORD",
        ),
        ("too-short", "a-secure-admin-password", "JWT_SECRET"),
        (
            "a-secure-random-jwt-secret-that-is-long-enough",
            "short",
            "ADMIN_PASSWORD",
        ),
    ],
)
def test_production_security_rejects_placeholders_and_short_secrets(
    monkeypatch, jwt_secret, admin_password, message
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_secret", jwt_secret)
    monkeypatch.setattr(settings, "admin_password", admin_password)
    monkeypatch.setattr(settings, "show_bootstrap_credentials", False)

    with pytest.raises(RuntimeError, match=message):
        _validate_production_security()


def test_production_security_accepts_explicit_secure_settings(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(
        settings,
        "jwt_secret",
        "a-secure-random-jwt-secret-that-is-long-enough",
    )
    monkeypatch.setattr(settings, "admin_password", "a-secure-admin-password")
    monkeypatch.setattr(settings, "show_bootstrap_credentials", False)
    monkeypatch.setattr(
        settings,
        "database_url",
        "mysql+aiomysql://mchat:a-secure-db-password@mysql:3306/mchat",
    )

    _validate_production_security()


@pytest.mark.asyncio
async def test_bootstrap_never_returns_password_in_production(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "super-secret-password")
    # Defense in depth if the flag is accidentally toggled after startup.
    monkeypatch.setattr(settings, "show_bootstrap_credentials", True)

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                mchat_signup_enabled=False,
                mchat_cloud_mode=False,
            )
        )
    )
    response = await bootstrap_hint(request)

    assert response.password is None
    assert response.show_credentials is False


def test_production_env_template_enables_security_mode():
    template = (
        Path(__file__).resolve().parents[2]
        / "ops"
        / "docker"
        / ".env.production.example"
    )
    values = dict(
        line.split("=", 1)
        for line in template.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    assert values["ENVIRONMENT"] == "production"
    assert values["SHOW_BOOTSTRAP_CREDENTIALS"] == "false"
    assert values["UPLOAD_DIR"] == "/app/uploads"


@pytest.mark.asyncio
async def test_production_upgrade_rotates_legacy_admin_password(db_session):
    admin = User(
        username="legacy-admin",
        password_hash=get_password_hash("admin123"),
        role="admin",
    )
    custom_admin = User(
        username="custom-admin",
        password_hash=get_password_hash("already-secure-password"),
        role="admin",
    )
    db_session.add_all([admin, custom_admin])
    await db_session.flush()

    rotated = await AuthService(db_session).rotate_legacy_admin_passwords(
        "replacement-production-password"
    )

    assert rotated == ["legacy-admin"]
    assert not verify_password("admin123", admin.password_hash)
    assert verify_password("replacement-production-password", admin.password_hash)
    assert verify_password("already-secure-password", custom_admin.password_hash)
