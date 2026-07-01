"""Playable-page verifier — HTTP-level smoke check after a build completes.

When a DevBridge build reaches ``built``, the playable URL (:5099 / xyx.9235.net)
should be reachable and serving the *new* bundle. This module does a lightweight,
dependency-light HTTP probe from the center process:

  1. GET the playable URL — expect HTTP 200 and a non-empty HTML body.
  2. Probe the main JS bundle (Cocos ``main/index.js``) — expect 200, not 404.
  3. If a bundle version label is found, compare it against the source version.

It is intentionally advisory: a failed probe does NOT fail the build — it only
annotates the build record so users see "page reachable / version consistent"
instead of blindly trusting a green "built".

Why center-side httpx and not SSH/the ops script: the playable URL is reachable
over the public internet (xyx.9235.net) or internal IP, so a plain GET works
without SSH credentials and from the API/worker process alike. Each probe is a
few HTTP requests completing in seconds.

The result is cached by the caller into the build's ``metadata.json`` under a
``playable_check`` key, so the 3s polling loop does NOT re-probe every tick.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

#: Per-request timeout. Playable pages are static + small; 10s is generous.
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

#: A short browser-like UA — some static servers behave oddly with default clients.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

#: Version label shape used by the GameCenter bundle (e.g. ``ver:1.42``).
_VERSION_RE = re.compile(r"ver:1\.\d+")


@dataclass
class PlayableCheckResult:
    """Outcome of a playable-page probe. All fields are JSON-safe (cached to disk)."""

    ok: bool = False
    """True only when the page is reachable AND (version known → consistent)."""

    reachable: bool = False
    """HTTP 200 + non-empty body from the playable index."""

    http_status: int | None = None
    missing_assets: list[str] = field(default_factory=list)
    """Asset paths that returned non-200 (e.g. main/index.js 404)."""

    source_version: str | None = None
    bundle_version: str | None = None
    version_match: bool | None = None
    """``True`` consistent / ``False`` stale / ``None`` when versions unknown."""

    probed_url: str | None = None
    detail: str = ""
    checked_at: str = ""

    def to_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)


def verify_playable(
    play_urls: list[str],
    *,
    source_version: str | None = None,
    base_url: str | None = None,
) -> PlayableCheckResult:
    """Probe the first reachable playable URL and return a check result.

    ``base_url`` (e.g. ``https://xyx.9235.net``) lets the caller pin which base to
    try first; otherwise the first URL in ``play_urls`` is used. The probe never
    raises — network errors collapse into ``ok=False`` with a ``detail`` message.
    """
    from datetime import datetime

    result = PlayableCheckResult(
        source_version=(source_version or None),
        checked_at=datetime.now().isoformat(timespec="seconds"),
    )

    # Prefer the caller-pinned base; else fall back to the first play URL.
    candidates: list[str] = []
    if base_url:
        base = base_url.rstrip("/")
        candidates.extend(u for u in play_urls if u.rstrip("/").startswith(base))
    candidates.extend(u for u in play_urls if u not in candidates)
    if not candidates:
        result.detail = "no playable URL configured"
        return result

    headers = {"User-Agent": _UA}
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True, headers=headers) as client:
            index_url = candidates[0]
            result.probed_url = index_url

            # 1. Playable index page
            try:
                resp = client.get(index_url)
            except httpx.HTTPError as exc:
                result.detail = f"index unreachable: {exc}"
                return result
            result.http_status = resp.status_code
            if resp.status_code != 200:
                result.detail = f"index returned HTTP {resp.status_code}"
                return result
            if not (resp.text or "").strip():
                result.detail = "index body empty"
                return result
            result.reachable = True

            # 2. Main JS bundle — Cocos web-mobile layout: assets/main/index.js
            bundle_path = "assets/main/index.js"
            bundle_url = index_url.rstrip("/") + "/" + bundle_path
            bundle_version: str | None = None
            try:
                bresp = client.get(bundle_url)
                if bresp.status_code != 200:
                    result.missing_assets.append(bundle_path)
                else:
                    labels = sorted(set(_VERSION_RE.findall(bresp.text)))
                    if labels:
                        bundle_version = ", ".join(labels)
            except httpx.HTTPError:
                result.missing_assets.append(bundle_path)

            result.bundle_version = bundle_version
            # 3. Version consistency — only judge when BOTH sides are known.
            if source_version and bundle_version:
                result.version_match = source_version == bundle_version
            elif source_version and not bundle_version:
                # Source has a label but the served bundle has none / asset 404:
                # we cannot confirm the new build is live.
                result.version_match = False

            missing = bool(result.missing_assets)
            stale = result.version_match is False
            result.ok = result.reachable and not missing and not stale
            if result.ok:
                result.detail = "reachable, assets present"
                if result.version_match:
                    result.detail += ", version consistent"
            elif stale:
                result.detail = (
                    "page reachable but served bundle version differs from source — "
                    "the new build may not be live yet (publish or wait for :5099)"
                )
            elif missing:
                result.detail = "page reachable but some assets missing"
            return result
    except Exception as exc:  # pragma: no cover — defensive, never raises to caller
        result.detail = f"probe error: {exc}"
        return result
