"""Douyin (抖音) publish runner.

Same proven pattern as Xiaohongshu: persistent profile + human cadence +
human-in-the-loop on captcha + shared media resolution. Posts an image note
to Douyin creator (https://creator.douyin.com).

NOTE: selectors below target the public creator UI as of 2026-06 but Douyin's
DOM changes frequently and is stricter than XHS. They are written to match the
known structure but MUST be calibrated against the live DOM before production
use (run inspect_publish.py adapted for douyin, or capture a manual click like
we did for xiaohongshu). The NeedsLoginError / CaptchaEncountered flow is
identical so login + first-run is the same operator step.
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


@register("douyin")
class DouyinRunner(BaseRunner):
    def publish(self, job: dict[str, Any]) -> dict[str, Any]:
        sel = get_selectors("douyin")
        images = resolve_media_paths(job.get("media"))
        if not images:
            raise ValueError("抖音图文至少需要一张图片 (job.media 需含本地 path 或可下载 url)")

        try:
            with managed_browser(self.cfg, "douyin") as context:
                page = context.new_page()
                page.set_viewport_size({"width": 1440, "height": 900})
                page.goto(sel["publish_url"], wait_until="domcontentloaded", timeout=30000)
                human_delay(self.cfg)

                self._ensure_logged_in(page)
                self._upload_images(page, sel, images)
                self._fill_content(page, sel, job)
                self._check_captcha(page)
                return self._submit(page, sel)
        finally:
            cleanup_paths(images)

    # -- steps (mirror xiaohongshu; calibrate selectors against live DOM) ----

    def _ensure_logged_in(self, page) -> None:
        human_delay(self.cfg)
        if "login" in page.url.lower():
            raise NeedsLoginError("未登录。请运行: python -m runners.login douyin 手动登录一次")

    def _upload_images(self, page, sel, images: list[str]) -> None:
        upload = page.locator(sel["upload_input"]).first
        upload.set_input_files(images)
        human_delay(self.cfg, multiplier=2.5)
        # Wait for the editor to render after upload.
        try:
            page.wait_for_selector(sel["title_input"], timeout=15000)
        except Exception as exc:
            raise RuntimeError(f"上传后未出现标题输入框，上传可能失败: {exc}") from exc

    def _fill_content(self, page, sel, job: dict[str, Any]) -> None:
        title = (job.get("title") or "")[:55]  # Douyin title cap ~55
        content = job.get("content") or ""
        if title:
            try:
                t = page.locator(sel["title_input"]).first
                t.click()
                human_delay(self.cfg, multiplier=0.3)
                t.fill(title)
            except Exception:
                pass
            human_delay(self.cfg)
        if content:
            try:
                page.locator(sel["body_editor"]).first.fill(content)
            except Exception:
                pass
            human_delay(self.cfg)
        random_mouse_jitter(page, self.cfg)

    def _check_captcha(self, page) -> None:
        """Detect a VISIBLE risk-control prompt. Never auto-solved."""
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
        # Douyin shows a success state in-place (not always a URL change).
        human_delay(self.cfg, multiplier=2.5)
        # Heuristic: look for a success indicator or absence of the editor.
        try:
            visible = page.evaluate(
                "() => document.body.innerText.slice(0, 2000)"
            )
        except Exception:
            visible = ""
        if any(kw in visible for kw in ["发布成功", "已发布", "发布中"]):
            return {"success": True, "message": "抖音内容已发布（请人工确认）"}
        return {
            "success": False,
            "message": "发布状态不确定：未检测到明确成功标识，请人工检查（抖音 DOM 需校准）",
        }
