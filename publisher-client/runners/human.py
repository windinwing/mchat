"""Human-behavior simulation — random delays, typing, scrolling.

Makes automated interaction look organic to risk-control systems: no fixed
timings, variable input speed, occasional scrolls/pauses. This is a best-effort
deterrent, NOT a guarantee — platforms evolve their detection continuously.

Tunables come from config ``[playwright]``: min_delay / max_delay (seconds).
"""

from __future__ import annotations

import random
from typing import Any


def _delay_range(cfg: dict[str, Any]) -> tuple[float, float]:
    pw = cfg.get("playwright", {})
    lo = float(pw.get("min_delay", 1.0))
    hi = float(pw.get("max_delay", 3.0))
    if hi < lo:
        lo, hi = hi, lo
    return lo, hi


def human_delay(cfg: dict[str, Any], *, multiplier: float = 1.0) -> None:
    """Block for a random duration within the configured range (sync)."""
    import time

    lo, hi = _delay_range(cfg)
    time.sleep(random.uniform(lo, hi) * multiplier)


def human_type(page, selector: str, text: str, cfg: dict[str, Any]) -> None:
    """Type ``text`` into ``selector`` one char at a time with variable delay."""
    field = page.locator(selector).first
    field.click()
    human_delay(cfg, multiplier=0.3)
    field.fill("")  # clear
    for ch in text:
        field.type(ch, delay=random.randint(40, 140))
        if random.random() < 0.05:  # occasional longer pause
            human_delay(cfg, multiplier=0.5)


def human_scroll(page, cfg: dict[str, Any], *, times: int = 2) -> None:
    """Scroll the page a few times with pauses, like a human reading."""
    for _ in range(times):
        page.mouse.wheel(0, random.randint(150, 400))
        human_delay(cfg, multiplier=0.6)


def random_mouse_jitter(page, cfg: dict[str, Any]) -> None:
    """Move the mouse to a random spot — defeats simple movement analysis."""
    x = random.randint(100, 1000)
    y = random.randint(100, 600)
    page.mouse.move(x, y, steps=random.randint(5, 15))
    human_delay(cfg, multiplier=0.3)
