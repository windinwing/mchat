from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.services import patent9235_auth as auth


def test_sso_login_url_omits_redirect_to(monkeypatch):
    monkeypatch.setattr(
        auth.settings,
        "patent9235_sso_login_url",
        "https://www.9235.net/user/login",
    )
    monkeypatch.setattr(auth.settings, "patent9235_sso_product_id", "pdmchat")
    url = auth.sso_login_url()
    assert url == "https://www.9235.net/user/login?sso=1&productId=pdmchat"
    assert "redirect_to" not in url


def test_normalize_9235_account_strips_plus86():
    assert auth.normalize_9235_account("+8613812345678") == "13812345678"
    assert auth.normalize_9235_account("user@9235.net") == "user@9235.net"


def test_verify_xtk_accepts_hs512_token(monkeypatch):
    secret = "taochudiqiulema"
    monkeypatch.setattr(auth.settings, "patent9235_jwt_secret", secret)
    token = jwt.encode(
        {
            "sub": "+8613912345678",
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
        },
        secret,
        algorithm="HS512",
    )
    claims = auth.verify_xtk(token)
    assert claims["account"] == "13912345678"


def test_verify_xtk_requires_secret(monkeypatch):
    monkeypatch.setattr(auth.settings, "patent9235_jwt_secret", "")
    with pytest.raises(Exception) as exc:
        auth.verify_xtk("abc")
    assert exc.value.status_code == 503
