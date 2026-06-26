"""Centralized CSS/XPath selectors per platform.

Platforms update their front-end frequently; isolating selectors here means a
UI change only requires editing this file, not the runner logic. Each platform
is a dict of ``role -> selector``. Prefer stable attributes (placeholder text,
role, aria-label) over brittle nth-child chains.

When a selector breaks (platform updates UI), the runner reports a clear
``selector_stale`` error so an operator updates it here.
"""

# ---- 小红书 (Xiaohongshu) ----
# Web creator studio: https://creator.xiaohongshu.com
# Selectors verified against the live DOM on 2026-06-25.
XIAOHONGSHU = {
    "creator_url": "https://creator.xiaohongshu.com/publish/publish",
    "login_url": "https://creator.xiaohongshu.com/login",
    # Login detection: the page redirects to /login when logged out, so the
    # most reliable "is logged in" check is the URL not containing "login".
    "login_check": "url",  # special value: runner checks page.url
    # Tab switch: "上传图文" is a div.creator-tab. Text-match is brittle across
    # redesigns but stable for now; JS click is used (element is off-viewport
    # in headless, so a normal click times out).
    "tab_upload_js": 'div.creator-tab',  # JS-click the one with text 上传图文
    # File input after switching to image tab: accept=.jpg,.jpeg,.png,.webp
    "upload_input": 'input[type="file"]',
    # Title editor — appears only AFTER an image is uploaded.
    # placeholder="填写标题会有更多赞哦", tag=INPUT.d-text
    "title_input": 'input[placeholder*="填写标题"]',
    # Body editor — ProseMirror (contenteditable div).
    "body_editor": 'div.tiptap.ProseMirror',
    # Publish button — a custom element <xhs-publish-btn> at the bottom of the
    # edit area (verified via live click capture). NOT the red "发布笔记" in the
    # left sidebar (that one is a navigation entry that switches to video mode).
    "publish_button": "xhs-publish-btn",
    # Success: clicking publish navigates to /publish/success.
    "success_url": "/publish/success",
}

# ---- 抖音 (Douyin) creator ----
DOUYIN = {
    "creator_url": "https://creator.douyin.com/creator-micro/home",
    "publish_url": "https://creator.douyin.com/creator-micro/content/upload",
    "upload_input": 'input[type="file"][accept*="image"], input[type="file"][accept*="video"]',
    "title_input": '.editor-kit-title input, input[placeholder*="标题"]',
    "body_editor": '.editor-kit-content[data-content="desc"], div[contenteditable="true"]',
    "publish_button": 'button:has-text("发布")',
    "login_avatar": '.avatar, [data-e2e="avatar"]',
}

# ---- 微博 (Weibo) web composer ----
# https://weibo.com — selectors need live-DOM calibration (DOM changes often).
WEIBO = {
    "compose_url": "https://weibo.com",
    "upload_input": 'input[type="file"]',
    "editor": 'div[contenteditable="true"], .Form_input_Box textarea, textarea[name="content"]',
    "publish_button": 'a:has-text("发博"), button:has-text("发布"), [class*=publish]',
}

SELECTORS: dict[str, dict[str, str]] = {
    "xiaohongshu": XIAOHONGSHU,
    "douyin": DOUYIN,
    "weibo": WEIBO,
}


def get_selectors(platform: str) -> dict[str, str]:
    """Return the selector dict for a platform (raises if unknown)."""
    if platform not in SELECTORS:
        raise KeyError(f"no selectors defined for platform: {platform}")
    return SELECTORS[platform]
