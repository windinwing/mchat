"""Xiaohongshu (小红书) publish runner — calibrated against live DOM.

Publish flow (verified 2026-06-25):
  1. Open creator publish page (persistent profile → logged in)
  2. Login check: if URL contains "login" → NeedsLoginError
  3. Switch to "上传图文" tab via JS click (element is off-viewport in headless)
  4. Upload image(s) via file input (accept=.jpg/.png/.webp)
  5. Title + body editors appear ONLY after upload — fill them
  6. Click publish (div.publish-video containing span.btn-text "发布笔记")
  7. Success = URL navigates away from /publish

Human-in-the-loop: captchas are detected and reported, NEVER auto-solved.
"""

from __future__ import annotations

from pathlib import Path
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


@register("xiaohongshu")
class XiaohongshuRunner(BaseRunner):
    def publish(self, job: dict[str, Any]) -> dict[str, Any]:
        sel = get_selectors("xiaohongshu")
        images = resolve_media_paths(job.get("media"))
        if not images:
            raise ValueError("小红书图文笔记至少需要一张图片 (job.media 需含本地 path 或可下载 url)")

        try:
            with managed_browser(self.cfg, "xiaohongshu") as context:
                page = context.new_page()
                page.set_viewport_size({"width": 1440, "height": 900})
                page.goto(sel["creator_url"], wait_until="domcontentloaded", timeout=30000)
                human_delay(self.cfg)

                self._ensure_logged_in(page)
                self._switch_to_image_tab(page, sel)
                self._upload_images(page, sel, images)
                self._fill_content(page, sel, job)
                self._check_captcha(page)
                return self._submit(page, sel)
        finally:
            cleanup_paths(images)

    # -- steps -------------------------------------------------------------

    def _ensure_logged_in(self, page) -> None:
        human_delay(self.cfg)
        if "login" in page.url.lower():
            raise NeedsLoginError(
                "未登录。请运行: python -m runners.login xiaohongshu 手动登录一次"
            )

    def _switch_to_image_tab(self, page, sel) -> None:
        """Click the '上传图文' tab. It's off-viewport in headless, so use JS click."""
        clicked = page.evaluate(
            """(tabCls) => {
                for (const el of document.querySelectorAll(tabCls)) {
                    if (el.textContent.trim() === '上传图文') { el.click(); return true; }
                }
                return false;
            }""",
            sel["tab_upload_js"],
        )
        if not clicked:
            # may already be on image tab; verify file input accepts images
            accept = page.locator('input[type="file"]').first.get_attribute("accept") or ""
            if "mp4" in accept:
                raise RuntimeError("无法切换到上传图文 tab")
        human_delay(self.cfg)

    def _upload_images(self, page, sel, images: list[str]) -> None:
        upload = page.locator(sel["upload_input"]).first
        upload.set_input_files(images)
        # wait for upload + editor area to render
        human_delay(self.cfg, multiplier=2.0)
        try:
            page.wait_for_selector(sel["title_input"], timeout=15000)
        except Exception as exc:
            raise RuntimeError(f"上传后未出现标题输入框，上传可能失败: {exc}") from exc

    def _fill_content(self, page, sel, job: dict[str, Any]) -> None:
        title = (job.get("title") or "")[:20]  # XHS title cap
        content = _sanitize_content(job.get("content") or "")

        if title:
            title_el = page.locator(sel["title_input"]).first
            title_el.click()
            human_delay(self.cfg, multiplier=0.3)
            title_el.fill(title)
            human_delay(self.cfg)

        if content:
            body_el = page.locator(sel["body_editor"]).first
            body_el.click()
            human_delay(self.cfg, multiplier=0.3)
            # ProseMirror: fill clears existing; type for human cadence
            body_el.fill(content)
            human_delay(self.cfg)
        random_mouse_jitter(page, self.cfg)

    def _check_captcha(self, page) -> None:
        """Detect a VISIBLE risk-control prompt. We never auto-solve it.

        Scanning the full page HTML would false-positive on JS bundle strings
        (e.g. "captcha" inside minified script). Instead we only check text of
        elements that are actually rendered/visible to the user.
        """
        indicators = ["请拖动滑块", "安全验证", "拖动滑块完成验证", "请完成验证"]
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
        low = (visible_text or "").lower()
        for ind in indicators:
            if ind in visible_text or ind.lower() in low:
                raise CaptchaEncountered(
                    f"检测到风控验证 ({ind})。已暂停，请人工完成验证后重试。"
                )

    def _submit(self, page, sel) -> dict[str, Any]:
        human_delay(self.cfg)
        # The publish control is a custom <xhs-publish-btn> element spanning the
        # full edit-area width, but it hosts TWO logical zones — "暂存离开"
        # (left) and "发布" (right). The element has no inner DOM (no shadow),
        # and the zone is resolved by click X coordinate via document-level
        # delegation. Verified by live manual clicks landing at x≈733/760
        # (element x=338,w=680 → right half). Clicking the center (~678) hits
        # the boundary and does nothing. So we click at 60% width — solidly in
        # the 发布 zone, matching the captured successful coordinates.
        btn = page.locator(sel["publish_button"]).first
        btn.scroll_into_view_if_needed()
        human_delay(self.cfg, multiplier=0.5)
        box = btn.bounding_box()
        if box is None:
            return {"success": False, "message": "无法定位发布按钮位置"}
        click_x = box["x"] + box["width"] * 0.6
        click_y = box["y"] + box["height"] * 0.5
        # Trusted click with full pointer move (the zone logic reads clientX).
        page.mouse.move(click_x, click_y, steps=12)
        human_delay(self.cfg, multiplier=0.2)
        page.mouse.click(click_x, click_y)

        # Success = page navigates to /publish/success.
        try:
            page.wait_for_url(
                lambda url: sel["success_url"] in url, timeout=30000
            )
            human_delay(self.cfg, multiplier=1.0)
            return {"success": True, "message": "小红书笔记已发布", "remote_url": page.url}
        except Exception:
            human_delay(self.cfg, multiplier=2.0)
            if sel["success_url"] in page.url:
                return {"success": True, "message": "小红书笔记已发布", "remote_url": page.url}
            # Publish didn't navigate — usually a content validation toast.
            # Surface the visible error so the caller knows why (not a guess).
            hint = _visible_validation_error(page)
            return {
                "success": False,
                "message": hint or "发布未成功：未跳转到成功页，请人工检查",
            }


# Xiaohongshu rejects hashtags containing special chars (., spaces, etc.) with
# "话题内不允许包含特殊符号". LLM-generated copy often produces tags like
# #GLM5.2 — sanitize so the whole note isn't blocked on publish.
import re

_HASHTAG_RE = re.compile(r"#([^\s#]+)")


def _sanitize_content(content: str) -> str:
    """Strip/fix hashtags that contain chars Xiaohongshu forbids.

    Keeps Chinese, letters, digits, underscores in tags; drops a tag entirely
    if nothing valid remains.
    """
    def _fix_tag(m: "re.Match[str]") -> str:
        raw = m.group(1)
        # Keep word chars (incl. Chinese) and underscore only.
        cleaned = re.sub(r"[^\w\u4e00-\u9fff]", "", raw, flags=re.UNICODE)
        return f"#{cleaned}" if cleaned else ""

    return _HASHTAG_RE.sub(_fix_tag, content)


# Known Xiaohongshu content-validation toasts (visible after a failed publish).
_VALIDATION_PATTERNS = [
    "话题内不允许包含特殊符号",
    "请填写标题",
    "请输入正文",
    "内容不能为空",
    "请至少上传",
    "包含违规",
    "请添加图片",
]


def _visible_validation_error(page) -> str | None:
    """Return a visible validation toast text if present, else None."""
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
                    if (t && t.length < 40) out.push(t);
                }
                return out.join('\\n');
            }"""
        )
    except Exception:
        return None
    for pat in _VALIDATION_PATTERNS:
        if pat in (visible_text or ""):
            return f"发布被校验拦截：{pat}"
    return None
