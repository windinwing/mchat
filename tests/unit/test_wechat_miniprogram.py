"""Tests for WeChat mini program link bridge."""

from app.utils.wechat_miniprogram import mini_program_bridge_url, rewrite_miniprogram_links


def test_mini_program_bridge_url(monkeypatch):
    monkeypatch.setattr(
        "app.utils.wechat_miniprogram.settings.mchat_public_base_url",
        "https://chat.example.com",
    )
    scheme = (
        "weixin://dl/business/?appid=wx895b71044575fa731"
        "&path=pages/index/index&env_version=release"
    )
    url = mini_program_bridge_url(scheme, label="打开小程序")
    assert url.startswith("https://chat.example.com/mini-program?")
    assert "url=" in url
    assert "name=" in url


def test_rewrite_miniprogram_links_markdown(monkeypatch):
    scheme = (
        "weixin://dl/business/?appid=wx895b71044575fa731"
        "&path=pages/index/index&env_version=release"
    )
    text = f"[打开小程序]({scheme})"
    monkeypatch.setattr(
        "app.utils.wechat_miniprogram.settings.mchat_public_base_url",
        "https://chat.example.com",
    )
    out = rewrite_miniprogram_links(text)
    assert "weixin://dl/business/" not in out
    assert "https://chat.example.com/mini-program?" in out
