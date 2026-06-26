"""First-time login tool — establish a persistent login profile per platform.

Usage:
    python -m runners.login xiaohongshu
    python -m runners.login douyin

Opens a browser with the platform's persistent profile, navigates to its login
page, and waits for you to sign in manually. When you close the browser window
(or press Enter in the terminal), the cookies / localStorage / fingerprint are
saved to ``browser_data/<platform>/`` and reused by every future publish run.

This is the ONLY manual step. After it, the agent can publish unattended
(re-authentication prompts handled by NeedsLoginError).
"""

from __future__ import annotations

import sys

from runners.browser import launch_browser
from runners.selectors import get_selectors

_LOGIN_URLS = {
    "xiaohongshu": "https://creator.xiaohongshu.com/login",
    "douyin": "https://creator.douyin.com",
    "weibo": "https://weibo.com",
}


def login(platform: str, cfg: dict) -> None:
    if platform not in _LOGIN_URLS:
        print(f"❌ 不支持的平台: {platform}")
        print(f"   支持: {', '.join(_LOGIN_URLS)}")
        sys.exit(1)

    # Force non-headless so the user can interact
    cfg = dict(cfg)
    cfg.setdefault("playwright", {})
    cfg["playwright"]["headless"] = False

    sel = get_selectors(platform)
    url = _LOGIN_URLS[platform]
    print(f"🔑 启动 {platform} 登录")
    print(f"   浏览器将打开: {url}")
    print(f"   小红书是【短信验证码登录】: 输入手机号 → 收验证码 → 登录")
    print(f"   登录成功后浏览器会自动跳转，或直接关闭浏览器窗口即可保存登录态。")
    print()

    pw, context = launch_browser(cfg, platform)
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url)

        import threading
        import time

        closed = threading.Event()
        context.on("close", lambda: closed.set())

        logged_in = False
        waited = 0
        while not closed.is_set() and not logged_in:
            closed.wait(timeout=5)
            waited += 5
            try:
                cur = page.url
                # 登录成功会离开 login 页
                if "login" not in cur.lower():
                    print(f"   ✅ 检测到跳转 (离开登录页)，登录成功！")
                    logged_in = True
                    # 多等几秒让 cookie 落地
                    time.sleep(3)
                    break
            except Exception:
                pass
            if waited % 30 == 0 and not closed.is_set():
                print(f"   (已等 {waited}s… 在浏览器里完成登录，或关闭窗口保存)")
        if not logged_in and closed.is_set():
            print(f"   浏览器已关闭，保存当前登录态。")
    finally:
        try:
            context.close()
        except Exception:
            pass
        pw.stop()

    print(f"✅ {platform} 登录态已保存到 browser_data/{platform}/")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m runners.login <platform>")
        print(f"   平台: {', '.join(_LOGIN_URLS)}")
        sys.exit(1)
    from agent import load_config

    cfg = load_config()
    login(sys.argv[1], cfg)
