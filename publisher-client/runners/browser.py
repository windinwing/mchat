"""Browser lifecycle + persistent profile management.

Each platform gets its own persistent browser context (cookies, localStorage,
device fingerprint) stored under ``browser_data/<platform>/``. After a one-time
manual login (see ``login.py``) the profile is reused so the platform sees a
returning real user — the foundation of "fully simulate human behavior".

Uses Playwright sync API (the agent runs as a plain script, no event loop).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def profile_dir(cfg: dict[str, Any], platform: str) -> Path:
    """Return the persistent profile directory for a platform."""
    base = Path(cfg.get("playwright", {}).get("browser_data_dir", "browser_data"))
    p = base / platform
    p.mkdir(parents=True, exist_ok=True)
    return p


def _clear_stale_locks(profile: Path) -> None:
    """Remove Chromium singleton lock files left by a crashed previous run.

    A leftover SingletonLock makes launch_persistent_context fail with
    TargetClosedError. Safe to remove: Chromium recreates them; if a real
    instance is running it holds these via fcntl, not the file existence.
    """
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        f = profile / name
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass


def launch_browser(cfg: dict[str, Any], platform: str):
    """Launch a persistent Playwright browser context for ``platform``.

    Returns ``(playwright, context)``. The caller must ``context.close()`` and
    ``playwright.stop()`` when done (use ``managed_browser`` for auto cleanup).

    Persistence: the context reuses ``browser_data/<platform>/`` so login state
    survives across runs. We deliberately do NOT spoof a fresh fingerprint each
    time — a stable, real-looking fingerprint is far less likely to trip risk
    control than a rotating one.
    """
    from playwright.sync_api import sync_playwright

    pw_cfg = cfg.get("playwright", {})
    headless = bool(pw_cfg.get("headless", False))
    profile = profile_dir(cfg, platform)
    _clear_stale_locks(profile)

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        headless=headless,
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        # A real-looking UA; kept stable per profile.
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        args=["--disable-blink-features=AutomationControlled"],
    )
    # Mask webdriver flag (basic anti-detection; not a silver bullet).
    for page in context.pages:
        _stealth_page(page)
    context.on("page", lambda page: _stealth_page(page))
    return pw, context


def _stealth_page(page) -> None:
    """Inject a small script to hide the automation signal on new pages."""
    try:
        page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
    except Exception:
        pass


class managed_browser:
    """Context manager wrapping launch_browser with guaranteed cleanup."""

    def __init__(self, cfg: dict[str, Any], platform: str) -> None:
        self.cfg = cfg
        self.platform = platform
        self.pw = None
        self.context = None

    def __enter__(self):
        self.pw, self.context = launch_browser(self.cfg, self.platform)
        return self.context

    def __exit__(self, *exc):
        if self.context is not None:
            try:
                self.context.close()
            except Exception:
                pass
        if self.pw is not None:
            try:
                self.pw.stop()
            except Exception:
                pass
