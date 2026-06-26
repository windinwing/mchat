"""Weibo (微博) publish runner.

Weibo's open platform severely limits automated posting, so this goes through
the web composer via Playwright (same client-machine pattern as Xiaohongshu/
Douyin). Persistent profile + human cadence + human-in-the-loop.

NOTE: selectors target https://weibo.com (web composer) as of 2026-06 but Weibo's
DOM changes frequently and is risk-control heavy. They MUST be calibrated
against the live DOM before production use (same flow as xiaohongshu: login →
inspect DOM → calibrate). NeedsLoginError / CaptchaEncountered flow identical.
"""

from __future__ import annotations

from typing import Any

from runners import BaseRunner, register
from runners.browser import managed_browser
from runners.human import human_delay, random_mouse_jitter
from runners.media import cleanup_paths, resolve_media_paths
from runners.selectors import get_selectors


class NeedsLoginError(Exception):
    """Profile has no valid login — operator must run login tool."""


class CaptchaEncountered(Exception):
    """Risk-control prompt shown — pause for human intervention."""


@register("weibo")
class WeiboRunner(BaseRunner):
    def publish(self, job: dict[str, Any]) -> dict[str, Any]:
        sel = get_selectors("weibo")
        content = job.get("content") or ""
        images = resolve_media_paths(job.get("media"))

        try:
            with managed_browser(self.cfg, "weibo") as context:
                page = context.new_page()
                page.set_viewport_size({"width": 1440, "height": 900})
                page.goto(sel["compose_url"], wait_until="domcontentloaded", timeout=30000)
                human_delay(self.cfg)

                self._ensure_logged_in(page)
                if images:
                    self._upload_images(page, sel, images)
                self._fill_content(page, sel, content)
                self._check_captcha(page)
                return self._submit(page, sel)
        finally:
            cleanup_paths(images)

    def _ensure_logged_in(self, page) -> None:
        human_delay(self.cfg)
        # Weibo redirects to passport.weibo.com when logged out.
        cur = page.url.lower()
        if "passport" in cur or "login" in cur:
            raise NeedsLoginError("未登录。请运行: python -m runners.login weibo 手动登录一次")

    def _upload_images(self, page, sel, images: list[str]) -> None:
        try:
            upload = page.locator(sel["upload_input"]).first
            upload.set_input_files(images)
            human_delay(self.cfg, multiplier=2.0)
            page.wait_for_timeout(2000)
        except Exception:
            # Image upload is optional on Weibo; don't block text post.
            pass

    def _fill_content(self, page, sel, content: str) -> None:
        editor = page.locator(sel["editor"]).first
        editor.click()
        human_delay(self.cfg, multiplier=0.3)
        # Weibo's editor is a contenteditable; type for human cadence.
        editor.fill(content[:2000])
        human_delay(self.cfg)
        random_mouse_jitter(page, self.cfg)

    def _check_captcha(self, page) -> None:
        indicators = ["请拖动滑块", "安全验证", "拖动滑块完成验证", "请完成验证", "图形验证"]
        try:
            visible_text = page.evaluate(
                """() => {
                    const out = [];
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_ELEMENT,
                        { acceptNode: e => (e.offsetParent !== null || e.getClientRects().length)
                            ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT }
                    );
                    let n;
                    while ((n = walker.nextNode())) {
                        const t = (n.textContent || '').trim();
                        if (t && t.length < 60) out.push(t);
                    }
                    return out.join('\\n');
                }"""
            )
        except Exception:
            return
        for ind in indicators:
            if ind in (visible_text or ""):
                raise CaptchaEncountered(f"检测到风控验证 ({ind})。已暂停，请人工完成验证后重试。")

    def _submit(self, page, sel) -> dict[str, Any]:
        human_delay(self.cfg)
        btn = page.locator(sel["publish_button"]).first
        btn.scroll_into_view_if_needed()
        human_delay(self.cfg, multiplier=0.5)
        btn.click()
        human_delay(self.cfg, multiplier=2.5)
        # Weibo shows an inline success state.
        try:
            visible = page.evaluate("() => document.body.innerText.slice(0, 2000)")
        except Exception:
            visible = ""
        if any(kw in visible for kw in ["发布成功", "已发布", "微博发布成功"]):
            return {"success": True, "message": "微博已发布"}
        return {
            "success": False,
            "message": "发布状态不确定：未检测到明确成功标识（微博 DOM 需校准）",
        }
