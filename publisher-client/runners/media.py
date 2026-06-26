"""Media resolution for client-machine runners.

A publish job's ``media`` entries may carry either a local ``path`` or a remote
``url`` (including same-origin ``/uploads/...`` served by the center).
Playwright's ``set_input_files`` needs real local files, so this module
downloads any URL media to a temp dir and returns absolute paths.

Shared by all platform runners (xiaohongshu, douyin, …) to avoid duplication.
Cleanup of downloaded temp files is the caller's responsibility (the agent
process is short-lived; OS /tmp reaper handles stragglers).
"""

from __future__ import annotations

import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


def resolve_media_paths(media: list[dict[str, Any]] | None) -> list[str]:
    """Return absolute local image paths for a job's media list.

    For each entry:
      - ``path`` (existing local file) → used directly.
      - ``url`` (http/https or /uploads path) → downloaded to a temp file.
    Entries that resolve to nothing are skipped (with a stderr note).
    """
    out: list[str] = []
    for m in media or []:
        if not isinstance(m, dict):
            continue
        path = m.get("path")
        if path and Path(path).is_file():
            out.append(str(Path(path).resolve()))
            continue
        url = m.get("url")
        if url:
            local = _download(str(url))
            if local:
                out.append(local)
            else:
                import sys

                print(f"⚠️ 跳过无法下载的媒体 url: {url}", file=sys.stderr)
    return out


def _download(url: str) -> str | None:
    """Download ``url`` to a temp file and return its path, or None on failure."""
    # Same-origin /uploads paths need the center base URL prepended by the agent
    # before reaching here; this handles absolute http(s) only.
    if not url.startswith(("http://", "https://")):
        return None
    try:
        suffix = _guess_suffix(url)
        fd, tmp = tempfile.mkstemp(suffix=suffix, prefix="xhs_media_")
        os.close(fd)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(tmp, "wb") as f:
            f.write(resp.read())
        return tmp
    except Exception as e:
        import sys

        print(f"⚠️ 下载媒体失败 {url}: {e}", file=sys.stderr)
        return None


def _guess_suffix(url: str) -> str:
    """Best-effort file extension from a URL path."""
    lower = url.lower().split("?")[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if lower.endswith(ext):
            return ext
    return ".jpg"


def cleanup_paths(paths: list[str]) -> None:
    """Remove temp-downloaded files (skip ones that were user-provided paths)."""
    tmpdir = tempfile.gettempdir()
    for p in paths:
        try:
            if str(Path(p).resolve()).startswith(tmpdir):
                Path(p).unlink(missing_ok=True)
        except Exception:
            pass
