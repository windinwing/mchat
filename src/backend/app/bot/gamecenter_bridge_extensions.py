"""GameCenter bridge tools for internal chat."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any


def _json_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return dict(model)


def _fmt_project_status(data: dict[str, Any]) -> str:
    roots = ", ".join(data.get("readable_roots") or []) or "—"
    return (
        f"✅ `{data.get('slug')}` · has_build={data.get('has_build')}\n"
        f"- 可读目录: {roots}\n"
        f"- 工程路径: `{data.get('path')}`"
    )


def _fmt_file_listing(data: dict[str, Any]) -> str:
    items = data.get("items") or []
    base = data.get("path") or "/"
    dirs = [str(i.get("name") or "") for i in items if i.get("is_dir")]
    files = [str(i.get("name") or "") for i in items if not i.get("is_dir")]
    lines = [f"📁 `{base or '/'}` — 共 {len(items)} 项"]
    if dirs:
        shown = dirs[:16]
        suffix = f" …+{len(dirs) - len(shown)}" if len(dirs) > len(shown) else ""
        lines.append(f"- 目录: {' · '.join(shown)}{suffix}")
    if files:
        shown = files[:12]
        suffix = f" …+{len(files) - len(shown)}" if len(files) > len(shown) else ""
        lines.append(f"- 文件: {' · '.join(shown)}{suffix}")
    return "\n".join(lines)


def _fmt_read_file(data: dict[str, Any]) -> str:
    path = str(data.get("path") or "")
    text = str(data.get("content") or "")
    lines = text.count("\n") + 1 if text else 0
    return f"📄 已读取 `{path}`（{len(text)} 字符 / {lines} 行）"


def _fmt_patch_result(data: dict[str, Any], *, verify_snippet: str = "") -> str:
    if data.get("unchanged"):
        return (
            f"⛔ `{data.get('path')}` **未写入**（提交内容与磁盘完全一致）\n"
            "- 请勿向用户声称已修改代码；请 read 文件核对后重试 patch。"
        )
    summary = (data.get("summary") or "").strip()
    extra = f" — {summary}" if summary else ""
    change_id = (data.get("id") or "").strip()
    after_sha = (data.get("after_sha256") or "")[:12]
    verify = ""
    if change_id:
        verify = (
            f"\n- 变更记录 id: `{change_id}`（list_gamecenter_project_changes 可核对）"
            f"\n- after_sha256: `{after_sha}…`"
        )
    if verify_snippet:
        verify += f"\n- 磁盘回读校验:\n```\n{verify_snippet.rstrip()}\n```"
    return f"✏️ **已写入服务器** `{data.get('path')}`{extra}{verify}"


def _patch_verify_snippet(content: str, *, old_text: str = "", new_text: str = "") -> str:
    lines = content.splitlines()
    hits: list[str] = []
    needles = [t for t in (new_text, old_text) if t and "\n" not in t and len(t) < 120]
    for line in lines:
        if any(n in line for n in needles):
            hits.append(line)
    if hits:
        return "\n".join(hits[:6])
    if len(lines) <= 8:
        return content
    return "\n".join(lines[:4] + ["…"] + lines[-4:])


def _fmt_changes(changes: list[dict[str, Any]]) -> str:
    if not changes:
        return "📋 暂无变更记录"
    lines = ["📋 **变更记录**"]
    for item in changes[:12]:
        path = str(item.get("path") or item.get("id") or "—")
        status = str(item.get("status") or "")
        summary = (item.get("summary") or "").strip()
        note = f" — {summary}" if summary else ""
        lines.append(f"- `{path}` ({status}){note}")
    if len(changes) > 12:
        lines.append(f"- … 另有 {len(changes) - 12} 条")
    return "\n".join(lines)


def _read_build_log_tail(data_root: Path, slug: str, build_id: str, *, max_chars: int = 2400) -> tuple[str, str]:
    build_dir = data_root / slug / "builds" / build_id
    stdout = ""
    stderr = ""
    stdout_path = build_dir / "stdout.log"
    stderr_path = build_dir / "stderr.log"
    if stdout_path.is_file():
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")[-max_chars:]
    if stderr_path.is_file():
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")[-max_chars:]
    return stdout.strip(), stderr.strip()


def _read_version_snapshot(project_path: str) -> tuple[str, str]:
    """Return (source_versions, bundle_versions) like ver:1.3 from TS sources and built JS."""
    import re
    from pathlib import Path

    root = Path(project_path)
    source_labels: list[str] = []
    for name in ("UIMain.ts", "UILoading.ts"):
        path = root / "assets/scripts/ui" / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = re.search(r"ver:1\.\d+", text)
        if match:
            source_labels.append(f"{name}={match.group(0)}")
    bundle_js = root / "build/web-mobile/assets/main/index.js"
    bundle_labels: list[str] = []
    if bundle_js.is_file():
        try:
            text = bundle_js.read_text(encoding="utf-8", errors="replace")
            bundle_labels = sorted(set(re.findall(r"ver:1\.\d+", text)))
        except OSError:
            pass
    return (
        ", ".join(source_labels) if source_labels else "—",
        ", ".join(bundle_labels) if bundle_labels else "—",
    )


def _fmt_build_progress(
    slug: str,
    *,
    project: dict[str, Any],
    builds: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    stdout_tail: str = "",
    stderr_tail: str = "",
    play_urls: list[str] | None = None,
) -> str:
    lines = [f"📊 **编译/发布进度** · `{slug}`"]
    project_path = str(project.get("path") or "")
    source_ver, bundle_ver = _read_version_snapshot(project_path) if project_path else ("—", "—")
    lines.append(
        f"- 源码更新: {project.get('source_updated_at') or '—'}"
        f" · 试玩包更新: {project.get('build_updated_at') or '—'}"
        f" · has_build={project.get('has_build')}"
    )
    lines.append(f"- **源码版本号**: {source_ver}")
    lines.append(f"- **线上试玩包版本号** (build/web-mobile): {bundle_ver}")
    if source_ver != "—" and bundle_ver != "—" and source_ver != bundle_ver:
        lines.append(
            "  - ⚠️ 源码与试玩包版本不一致：改动可能未写入源码，或编译未完成/复用了旧包。"
        )
    if not builds:
        lines.append("- 构建记录: 暂无（尚未触发 build 或 patch 后自动编译）")
    else:
        latest = builds[0]
        status = str(latest.get("status") or "unknown")
        build_id = str(latest.get("id") or "")
        created = str(latest.get("created_at") or "")
        rc = latest.get("returncode")
        summary = (latest.get("summary") or "").strip()
        lines.append(f"- **最新构建**: `{build_id}` · **{status}** · {created}" + (f" · exit={rc}" if rc is not None else ""))
        if summary:
            lines.append(f"  - 说明: {summary}")
        if status == "built" and "Reuse existing" in (stdout_tail or ""):
            lines.append("  - ⚠️ 上次构建**复用了旧 web-mobile 包**，源码改动可能未进试玩；需 Windows 远程 pipeline 真编译。")
        elif status in {"queued", "running"}:
            lines.append("  - ⏳ 后台编译中，稍后再查或看 stdout 日志")
        elif status == "failed":
            lines.append("  - ❌ 构建失败，见下方日志")
        elif status == "built":
            lines.append("  - ✅ 构建完成；:5099 试玩目录应已更新（请强刷浏览器）")
        lines.append("- 近几次构建:")
        for item in builds[:5]:
            bid = str(item.get("id") or "")[:8]
            lines.append(
                f"  - `{bid}…` {item.get('status')} @ {item.get('created_at')}"
                + ((f" — {item.get('summary')}" if item.get("summary") else ""))
            )
    if changes:
        latest_change = changes[0]
        lines.append(
            f"- 最近代码变更: `{latest_change.get('path')}` ({latest_change.get('status')})"
            + (f" — {latest_change.get('summary')}" if latest_change.get("summary") else "")
        )
    if play_urls:
        lines.append("- 试玩链接（强刷 Cmd+Shift+R）：" + " ".join(play_urls))
    if stdout_tail:
        preview = stdout_tail[-2000:]
        lines.append(f"<details><summary>最新构建 stdout</summary>\n\n```text\n{preview}\n```\n\n</details>")
    if stderr_tail:
        preview = stderr_tail[-1200:]
        lines.append(f"<details><summary>最新构建 stderr</summary>\n\n```text\n{preview}\n```\n\n</details>")
    return "\n".join(lines)


def _fmt_build(data: dict[str, Any]) -> str:
    status = str(data.get("status") or "unknown")
    status_label = {
        "queued": "已入队（后台编译中）",
        "running": "编译中",
        "built": "成功",
        "failed": "失败",
    }.get(status, status)
    build_id = str(data.get("id") or "")
    cmd = str(data.get("command") or "")
    lines = [f"🔨 构建 {status_label}" + (f" · `{build_id}`" if build_id else "")]
    if status in {"queued", "running"}:
        lines.append("聊天中将自动刷新编译进度，直至完成。")
    if cmd:
        lines.append(f"<details><summary>构建命令</summary>\n\n```bash\n{cmd}\n```\n\n</details>")
    stdout = str(data.get("stdout_tail") or "").strip()
    if stdout:
        preview = stdout[:2000] + ("…" if len(stdout) > 2000 else "")
        lines.append(f"<details><summary>构建输出</summary>\n\n```text\n{preview}\n```\n\n</details>")
    play_urls = data.get("play_urls") or []
    if play_urls:
        lines.append("试玩链接（请强刷 Cmd+Shift+R）：" + " ".join(str(u) for u in play_urls))
    stderr = str(data.get("stderr") or "").strip()
    if stderr:
        preview = stderr[:1200] + ("…" if len(stderr) > 1200 else "")
        lines.append(f"<details><summary>构建日志</summary>\n\n```text\n{preview}\n```\n\n</details>")
    return "\n".join(lines)


def _play_urls_for_slug(slug: str, *, service: Any = None) -> list[str]:
    """Generate play URLs for a slug using the bridge service (category-aware).

    Post-restructure the URL is /<category>/<slug>/ (e.g. /misc/cat/).
    Falls back to legacy /<slug>/ if the service cannot resolve the category.
    """
    if service is not None and hasattr(service, "_play_urls"):
        return service._play_urls(slug)
    try:
        svc = _resolve_bridge_service("gamecenter")
        return svc._play_urls(slug)
    except Exception:
        cfg = _gc_settings()
        bases = [str(item).strip() for item in (cfg.get("playable_base_urls") or []) if str(item).strip()]
        if not bases and cfg.get("playable_base_url"):
            bases = [str(cfg.get("playable_base_url")).strip()]
        return [f"{base.rstrip('/')}/{slug}/" for base in bases]


BUILD_WATCH_POLL_SECONDS = 3.0
BUILD_WATCH_MAX_SECONDS = 7200.0

_BUILD_STATUS_LABEL = {
    "queued": "已入队",
    "running": "编译中",
    "built": "已完成",
    "failed": "失败",
}


def _pipeline_phase_hint(stdout_tail: str) -> str:
    for line in reversed(stdout_tail.splitlines()):
        text = line.strip()
        if not text:
            continue
        if text.startswith("==>") and len(text) < 80:
            return text[4:].strip()
        markers = ("[1/3]", "[2/3]", "[3/3]", "Pull", "Push", "Cocos", "BUILD", "编译", "Building")
        if any(marker in text for marker in markers):
            return text[:140]
    return ""


def _fmt_build_progress_tick(slug: str, progress: dict[str, Any]) -> str:
    latest = progress.get("latest_build") or {}
    status = str(latest.get("status") or "unknown")
    label = _BUILD_STATUS_LABEL.get(status, status)
    hint = _pipeline_phase_hint(str(progress.get("stdout_tail") or ""))
    now = datetime.now().strftime("%H:%M:%S")
    line = f"⏳ **编译进度** · `{slug}` · {label}"
    if hint:
        line += f" · {hint}"
    line += f" · {now}\n\n"
    return line


def _fmt_build_progress_done(slug: str, progress: dict[str, Any]) -> str:
    latest = progress.get("latest_build") or {}
    status = str(latest.get("status") or "")
    play_urls = progress.get("play_urls") or []
    if status == "built":
        lines = [f"✅ **编译完成** · `{slug}`"]
        source_ver = progress.get("source_version")
        bundle_ver = progress.get("bundle_version")
        if source_ver or bundle_ver:
            lines.append(f"- 版本: 源码 {source_ver or '—'} · 试玩包 {bundle_ver or '—'}")
        if play_urls:
            lines.append("- 试玩（强刷 Cmd+Shift+R）：" + " ".join(str(u) for u in play_urls))
        return "\n".join(lines) + "\n\n"
    if status == "failed":
        stderr = str(progress.get("stderr_tail") or "").strip()[-800:]
        block = f"❌ **编译失败** · `{slug}`"
        if stderr:
            block += f"\n\n```text\n{stderr}\n```"
        return block + "\n\n"
    return ""


def should_stream_gamecenter_build_progress(
    tool_name: str,
    tool_result: Any,
    tool_args: dict[str, Any],
) -> str | None:
    """Return slug when chat should poll build progress until done."""
    if not isinstance(tool_result, dict) or not tool_result.get("ok"):
        return None
    if tool_name not in {"patch_gamecenter_project_file", "build_gamecenter_project"}:
        return None
    cfg = _gc_settings()
    if cfg.get("watch_build_in_chat") is False:
        return None
    slug = str(tool_args.get("slug") or tool_result.get("project") or "").strip()
    if not slug:
        return None
    build_info = tool_result.get("auto_build") if tool_name == "patch_gamecenter_project_file" else tool_result
    if not isinstance(build_info, dict) or build_info.get("error"):
        return None
    status = str(build_info.get("status") or "")
    if build_info.get("queued") or status in {"queued", "running"}:
        return slug
    return None


async def stream_build_progress_in_chat(
    slug: str,
    *,
    poll_seconds: float = BUILD_WATCH_POLL_SECONDS,
    max_seconds: float = BUILD_WATCH_MAX_SECONDS,
) -> AsyncIterator[str]:
    """Poll DevBridge build records and yield chat-visible progress until terminal state."""
    import asyncio
    import time

    service = _resolve_bridge_service("gamecenter")
    started = time.monotonic()
    last_tick = ""

    yield f"\n📡 **正在跟踪编译进度**（每 {int(poll_seconds)} 秒刷新，完成后自动通知）…\n\n"

    while True:
        progress = service.get_build_progress(slug)
        latest = progress.get("latest_build") or {}
        status = str(latest.get("status") or "")
        tick = _fmt_build_progress_tick(slug, progress)
        if tick != last_tick:
            yield tick
            last_tick = tick
        if status not in {"queued", "running"}:
            done = _fmt_build_progress_done(slug, progress)
            if done:
                yield done
            break
        if time.monotonic() - started > max_seconds:
            yield (
                f"\n⏱️ 编译跟踪超时（>{int(max_seconds / 60)} 分钟），"
                f"请稍后说「查 {slug} 编译进度」。\n\n"
            )
            break
        await asyncio.sleep(poll_seconds)


def _try_auto_build_after_patch(
    service: Any,
    *,
    slug: str,
    user_id: str,
    summary: str | None,
) -> dict[str, Any] | None:
    cfg = _gc_settings()
    if not cfg.get("auto_build_after_patch"):
        return None
    if not (cfg.get("build_command") or "").strip():
        return {"error": "auto_build_after_patch 已开启但未配置 build_command"}
    try:
        result = service.build_project(
            slug,
            actor_user_id=user_id,
            summary=(summary or "auto build after patch").strip(),
        )
        result["play_urls"] = _play_urls_for_slug(slug, service=service)
        return result
    except HTTPException as exc:
        return {"error": str(exc.detail)}

from fastapi import HTTPException

from app.bot import chat_extensions
from app.bot.tool_runtime import (
    get_bot_conversation,
    get_bot_db,
    get_bot_group_devbridge_allowlists,
    get_bot_group_member_role,
    get_bot_platform_user_role,
    get_bot_user_id,
)
from app.core.config import settings
from app.models.conversation import Conversation
from app.services.devbridge_admin_settings import resolved_gamecenter_settings
from app.models.user import User
from app.services.devbridge_registry import get_devbridge_provider, list_devbridge_providers

_PROVIDER_PROPERTY: dict[str, Any] = {
    "type": "string",
    "description": "DevBridge provider key (default: gamecenter).",
}


def _enabled_providers() -> list[Any]:
    return [item for item in list_devbridge_providers() if item.enabled]


def _any_bridge_enabled() -> bool:
    return bool(_enabled_providers())


def _provider_write_enabled(provider_key: str) -> bool:
    provider = get_devbridge_provider(provider_key.strip().lower())
    return provider.enabled and "file:patch" in provider.capabilities


def _any_bridge_write_enabled() -> bool:
    return any(_provider_write_enabled(item.key) for item in _enabled_providers())


def _resolve_bridge_service(provider_key: str | None = None):
    key = (provider_key or "gamecenter").strip().lower()
    provider = get_devbridge_provider(key)
    if not provider.enabled:
        raise HTTPException(status_code=503, detail=f"DevBridge provider {key!r} is disabled")
    allowlists = get_bot_group_devbridge_allowlists()
    override = None
    if allowlists and key in allowlists:
        slugs = allowlists[key]
        if slugs:
            override = slugs
    return provider.service_factory(project_allowlist_override=override)

_READ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_gamecenter_projects",
            "description": "List readable GameCenter projects and their build status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gamecenter_project_status",
            "description": "Get source/build status for a specific GameCenter project.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string", "description": "Project folder name"}},
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gamecenter_build_progress",
            "description": (
                "Get compile/publish progress for a GameCenter project: latest build status, "
                "log tail, recent code changes, and playable URLs. "
                "Use when the user asks about 编译进度/发布进度/构建状态/试玩是否更新."
            ),
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string", "description": "Project folder name"}},
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_gamecenter_project_builds",
            "description": "List recent build records for a GameCenter project (same data as get_gamecenter_build_progress).",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_gamecenter_project_changes",
            "description": "List recent controlled file changes for a GameCenter project.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_gamecenter_project_files",
            "description": "List readable files/directories inside a GameCenter project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project folder name"},
                    "path": {"type": "string", "description": "Relative path under the project"},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_gamecenter_project_file",
            "description": "Read a UTF-8 text file inside a GameCenter project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project folder name"},
                    "path": {"type": "string", "description": "Relative file path under the project"},
                },
                "required": ["slug", "path"],
            },
        },
    },
]

_WRITE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "patch_gamecenter_project_file",
            "description": (
                "Write a controlled UTF-8 text file inside a GameCenter project. "
                "Prefer old_text+new_text for small edits (server reads file, applies replace, writes). "
                "Use full content only after read_gamecenter_project_file. "
                "Success requires a change id in the tool result — never claim edits without it. "
                "Version labels (ver:1.x): patch BOTH UIMain.ts and UILoading.ts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string", "description": "Full new file text (use with read first)"},
                    "old_text": {"type": "string", "description": "Exact substring to replace (preferred for small edits)"},
                    "new_text": {"type": "string", "description": "Replacement for old_text"},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences of old_text"},
                    "summary": {"type": "string"},
                },
                "required": ["slug", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_gamecenter_project",
            "description": "Run the configured fixed build command for a GameCenter project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "revert_gamecenter_project_change",
            "description": "Revert a previous controlled file change in a GameCenter project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "change_id": {"type": "string"},
                },
                "required": ["slug", "change_id"],
            },
        },
    },
]

_PUBLISH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "publish_gamecenter_project_build",
            "description": "Publish a built snapshot to the playable release directory and switch current.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "build_id": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["slug", "build_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_gamecenter_project_releases",
            "description": "List published playable releases for a GameCenter project.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rollback_gamecenter_project_release",
            "description": "Switch the current playable release back to a previous release id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "release_id": {"type": "string"},
                },
                "required": ["slug", "release_id"],
            },
        },
    },
]

# ── generic devbridge tools (provider-agnostic) ──

_NEW_READ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_devbridge_projects",
            "description": "List all readable DevBridge projects across all enabled providers. Returns project slugs, paths, and build status. Use this as the first step in any development workflow.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_devbridge_project_files",
            "description": "Search/grep across readable project files for a pattern. Returns matching lines with file path and line number. Use this to find variable references, function calls, or any code pattern before editing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project slug/folder name"},
                    "pattern": {"type": "string", "description": "Search pattern (supports regex). For plain text, simple words work."},
                    "path": {"type": "string", "description": "Optional subdirectory to limit search scope"},
                },
                "required": ["slug", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diff_devbridge_project_change",
            "description": "Show before/after diff of a specific file change. Returns the old content, new content, and a unified diff of changed lines. Use this to present changes to the user for review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project slug/folder name"},
                    "change_id": {"type": "string", "description": "Change ID returned by a previous patch"},
                },
                "required": ["slug", "change_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_devbridge_templates",
            "description": "List available project templates for create_devbridge_project. Always call this before creating a project so the user can choose.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_devbridge_project",
            "description": "Create a new project from a template. Use after the user confirms the template choice. Available templates: cocos-simple-game (Cocos game with Canvas+Game.ts+UIController.ts), cocos-empty (minimal Cocos project), web-frontend (HTML/CSS/JS), node-backend (Node.js TypeScript service).",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "New project slug/folder name, lowercase with hyphens, e.g. my-game"},
                    "template": {"type": "string", "description": "Template name, e.g. cocos-simple-game"},
                },
                "required": ["slug", "template"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_devbridge_project_status",
            "description": "Get project status: readable roots, build state, source timestamp, nested project path. Use after selecting a slug.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string", "description": "Project slug/folder name"}},
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_devbridge_project_files",
            "description": "List readable files and directories inside a project subdirectory. Use to browse the project tree before reading or editing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project slug/folder name"},
                    "path": {"type": "string", "description": "Relative directory path, e.g. assets/scripts or empty for root"},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_devbridge_project_file",
            "description": "Read a UTF-8 text file from a project. Use before patching to see the exact file content on disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project slug/folder name"},
                    "path": {"type": "string", "description": "Relative file path, e.g. assets/scripts/Game.ts"},
                },
                "required": ["slug", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_devbridge_asset",
            "description": "Upload a binary asset (image, audio, model, font) to a project as base64 data. Use for game textures, sound effects, 3D models, fonts etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project slug/folder name"},
                    "path": {"type": "string", "description": "Relative path inside project, e.g. assets/textures/bg.png"},
                    "data": {"type": "string", "description": "Base64-encoded binary data"},
                    "overwrite": {"type": "boolean", "description": "Set true to overwrite if asset already exists"},
                },
                "required": ["slug", "path", "data"],
            },
        },
    },
]

_NEW_WRITE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "patch_devbridge_project_file",
            "description": "Edit a controlled text file. Prefer old_text+new_text for small changes (e.g. ver:1.2 → ver:1.3). For large rewrites use content. The tool reads the file, applies the replacement, writes, and verifies SHA. Returns a change_id only if the file was actually modified.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project slug/folder name"},
                    "path": {"type": "string", "description": "Relative file path, e.g. assets/scripts/Game.ts"},
                    "old_text": {"type": "string", "description": "Exact substring to find and replace"},
                    "new_text": {"type": "string", "description": "Replacement text"},
                    "content": {"type": "string", "description": "Full new file content (use when old_text+new_text is impractical)"},
                    "replace_all": {"type": "boolean", "description": "Replace every occurrence of old_text (default: first only)"},
                    "summary": {"type": "string", "description": "Short description of what changed"},
                },
                "required": ["slug", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_devbridge_project",
            "description": "Run the configured build command for a project. Use after patching to verify the code compiles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project slug/folder name"},
                    "summary": {"type": "string", "description": "Short build note"},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_init_devbridge_project",
            "description": "Initialize a git repository for a project. Creates .gitignore (library/temp/build/node_modules), stages all files, and creates an initial commit. Only needed once per project.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string", "description": "Project slug/folder name"}},
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit_devbridge_project",
            "description": "Stage all changes and create a git commit. Use after code edits to save a checkpoint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project slug/folder name"},
                    "message": {"type": "string", "description": "Commit message"},
                },
                "required": ["slug", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_set_remote_devbridge_project",
            "description": "Set the git remote origin URL for pushing to GitLab/GitHub.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Project slug/folder name"},
                    "remote_url": {"type": "string", "description": "Git remote URL, e.g. git@10.98.8.123:game/my-project.git"},
                },
                "required": ["slug", "remote_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_push_devbridge_project",
            "description": "Push commits to the configured remote origin.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string", "description": "Project slug/folder name"}},
                "required": ["slug"],
            },
        },
    },
]

_NEW_GIT_READ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "git_status_devbridge_project",
            "description": "Show git working tree status: changed files, untracked files, remote config.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string", "description": "Project slug/folder name"}},
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log_devbridge_project",
            "description": "Show recent git commit history for a project.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string", "description": "Project slug/folder name"}},
                "required": ["slug"],
            },
        },
    },
]

_NEW_READ_TOOL_NAMES = {tool["function"]["name"] for tool in _NEW_READ_TOOLS} | {tool["function"]["name"] for tool in _NEW_GIT_READ_TOOLS}
_NEW_WRITE_TOOL_NAMES = {tool["function"]["name"] for tool in _NEW_WRITE_TOOLS}
_NEW_ALL_TOOL_NAMES = _NEW_READ_TOOL_NAMES | _NEW_WRITE_TOOL_NAMES

_READ_TOOL_NAMES = {tool["function"]["name"] for tool in _READ_TOOLS}
_WRITE_TOOL_NAMES = {tool["function"]["name"] for tool in _WRITE_TOOLS}
_PUBLISH_TOOL_NAMES = {tool["function"]["name"] for tool in _PUBLISH_TOOLS}
_ALL_TOOL_NAMES = _READ_TOOL_NAMES | _WRITE_TOOL_NAMES | _PUBLISH_TOOL_NAMES | _NEW_ALL_TOOL_NAMES


_GAMECENTER_TOOL_NAMES = (
    "list_gamecenter_projects, get_gamecenter_project_status, list_gamecenter_project_files, "
    "read_gamecenter_project_file, patch_gamecenter_project_file, build_gamecenter_project, "
    "get_gamecenter_build_progress, publish_gamecenter_project_build"
)


def _hint(prompt: str) -> str:
    extra = (
        "\n\n## GameCenter bridge tools (独立工具，不是 mchat-ops 子命令)\n"
        f"可用工具: {_GAMECENTER_TOOL_NAMES}.\n"
        "用户提到 GameCenter / 试玩链接 / Cocos / pkg 项目 / 改版本号时，**必须**调用上述工具；"
        "**禁止**通过 mchat-ops 执行 list_gamecenter_projects 等（mchat-ops 只有 health/logs/db 等运维命令）。\n"
        "流程: list_gamecenter_projects → read → patch(old_text+new_text) → get_gamecenter_build_progress 核对版本。\n"
        "编译/发布进度: get_gamecenter_build_progress(slug)。"
    )
    cfg = resolved_gamecenter_settings()
    if cfg.get("write_enabled"):
        extra += (
            " For code edits you MUST call patch_gamecenter_project_file (prefer old_text+new_text); "
            "never describe code changes in prose without a successful patch tool result containing a change id. "
            "If the tool says 未写入/unchanged, the file was NOT modified — read the file and retry."
        )
        if cfg.get("auto_build_after_patch"):
            extra += (
                " After a successful patch (with change id), the system auto-runs build_command; "
                "do not claim build/publish success unless the auto-build result is shown."
            )
        else:
            extra += (
                " After patching, call build_gamecenter_project, then tell the user to hard-refresh the playable URL."
            )
    if settings.gamecenter_publish_enabled:
        extra += " Publishing to playables is optional when build_command already pushes build/web-mobile."
    return prompt + extra


def _gc_settings() -> dict:
    return resolved_gamecenter_settings()


async def _bridge_read_allowed(conversation: Conversation | None = None) -> bool:
    """Group members may query progress; write ops still require staff."""
    db = get_bot_db()
    user_id = get_bot_user_id()
    if db is None or not user_id or not _any_bridge_enabled():
        return False
    if conversation is not None and not conversation_allows_bridge(conversation):
        return False
    user = await db.get(User, user_id)
    return user is not None


def devbridge_write_allowed() -> bool:
    """Sync check using roles captured in set_bot_tool_context (engine turn setup)."""
    platform_role = (get_bot_platform_user_role() or "").strip()
    if platform_role in {"admin", "agent"}:
        return True
    group_role = (get_bot_group_member_role() or "").strip()
    return group_role in {"owner", "editor"}


async def _bridge_write_allowed(conversation: Conversation | None = None) -> bool:
    if not _any_bridge_enabled():
        return False
    if conversation is not None and not conversation_allows_bridge(conversation):
        return False
    if devbridge_write_allowed():
        return True
    # Fallback when context vars were not set (e.g. tests)
    db = get_bot_db()
    user_id = get_bot_user_id()
    if db is None or not user_id:
        return False
    user = await db.get(User, user_id)
    if user and user.role in {"admin", "agent"}:
        return True
    if (
        conversation is not None
        and conversation.scope_type == "group"
        and conversation.scope_id
    ):
        from sqlalchemy import select

        from app.models.group import GroupMember

        result = await db.execute(
            select(GroupMember.role).where(
                GroupMember.group_id == conversation.scope_id,
                GroupMember.user_id == user_id,
            )
        )
        role = result.scalar_one_or_none()
        return role in {"owner", "editor"}
    return False


def conversation_allows_bridge(conversation: Conversation) -> bool:
    """Whether DevBridge tools should be exposed in this chat (group-only by default)."""
    cfg = _gc_settings()
    if not _any_bridge_enabled():
        return False
    if not conversation.user_id:
        return False
    if not cfg.get("bridge_group_scope_only", True):
        return True
    return conversation.scope_type == "group" and bool(conversation.scope_id)


def _extra_tools(conversation: Conversation, _ctx: Any) -> list[dict[str, Any]]:
    if not conversation_allows_bridge(conversation):
        return []
    tools = list(_READ_TOOLS)
    tools.extend(_NEW_READ_TOOLS)
    tools.extend(_NEW_GIT_READ_TOOLS)
    if not devbridge_write_allowed():
        return tools
    cfg = _gc_settings()
    if cfg.get("enabled") and cfg.get("write_enabled"):
        tools.extend(_WRITE_TOOLS)
    if _any_bridge_write_enabled():
        tools.extend(_NEW_WRITE_TOOLS)
    if cfg.get("enabled") and cfg.get("publish_enabled"):
        tools.extend(_PUBLISH_TOOLS)
    return tools


async def _execute(name: str, args: dict[str, Any], _ctx: Any) -> Any | None:
    if name not in _ALL_TOOL_NAMES:
        return None
    conversation = get_bot_conversation()
    if name in _READ_TOOL_NAMES or name in _NEW_READ_TOOL_NAMES:
        if not await _bridge_read_allowed(conversation):
            return {"error": "GameCenter bridge not available in this conversation"}
    elif not await _bridge_write_allowed(conversation):
        return {
            "error": "GameCenter bridge write/publish denied",
            "content": (
                "❌ 当前账号**没有改代码权限**。\n"
                "- 群组成员 `member`：只能查看项目/进度，不能 patch/build/publish。\n"
                "- 需要群组 **owner/editor**，或平台 **admin/agent**。\n"
                "请在群组设置里把需要改代码的同事设为 **编辑者（editor）**。"
            ),
        }

    provider_key = (
        "gamecenter"
        if name.startswith("gamecenter_")
        else str(args.get("provider") or "gamecenter").strip().lower()
    )
    try:
        service = _resolve_bridge_service(provider_key)
    except HTTPException as exc:
        return {"ok": False, "error": str(exc.detail), "content": f"❌ {exc.detail}"}
    user_id = get_bot_user_id() or "system"

    if name == "list_gamecenter_projects":
        items = [item.model_dump() for item in service.list_projects()]
        slugs = [str(item.get("slug") or "") for item in items if item.get("slug")]
        preview = ", ".join(slugs[:12])
        if len(slugs) > 12:
            preview += f", …（共 {len(slugs)} 个）"
        return {
            "ok": True,
            "content": (
                f"当前可访问 {len(items)} 个项目"
                + (f"：{preview}" if preview else "")
                + "。请继续读取目标项目文件。"
            ),
            "projects": items,
        }
    if name == "get_gamecenter_project_status":
        item = service.get_project(str(args.get("slug") or ""))
        data = _json_dump(item)
        return {"ok": True, "content": _fmt_project_status(data), "project": data}
    if name == "list_gamecenter_project_files":
        listing = service.list_files(str(args.get("slug") or ""), str(args.get("path") or ""))
        data = _json_dump(listing)
        return {"ok": True, "content": _fmt_file_listing(data), "listing": data}
    if name == "read_gamecenter_project_file":
        file_data = service.read_file(str(args.get("slug") or ""), str(args.get("path") or ""))
        data = _json_dump(file_data)
        return {"ok": True, "content": _fmt_read_file(data), "file": data}
    if name == "patch_gamecenter_project_file":
        slug = str(args.get("slug") or "")
        path = str(args.get("path") or "")
        content_arg = str(args.get("content") or "")
        old_text = str(args.get("old_text") or "")
        new_text = str(args.get("new_text") or "")
        replace_all = bool(args.get("replace_all"))

        if old_text or new_text:
            if not old_text or not new_text:
                return {
                    "ok": False,
                    "error": "old_text 与 new_text 必须同时提供",
                    "content": "❌ 局部替换需要同时提供 old_text 和 new_text。",
                }
            if content_arg:
                return {
                    "ok": False,
                    "error": "不能同时使用 content 与 old_text/new_text",
                    "content": "❌ 请二选一：局部替换用 old_text+new_text，整文件覆盖用 content。",
                }
            try:
                current = service.read_file(slug, path)
            except HTTPException as exc:
                detail = str(exc.detail)
                return {
                    "ok": False,
                    "error": detail,
                    "content": (
                        f"❌ 读取失败: {detail}\n"
                        "请先 list/read 确认 path，例如 `assets/scripts/ui/UIMain.ts`。"
                    ),
                }
            if old_text not in current.content:
                preview = _patch_verify_snippet(current.content, old_text=old_text)
                return {
                    "ok": False,
                    "error": "old_text not found on disk",
                    "content": (
                        f"❌ `{current.path}` 中**找不到** old_text，未写入任何内容。\n"
                        f"- 你提供的 old_text 前 80 字: `{old_text[:80]}`\n"
                        f"- 磁盘文件片段:\n```\n{preview}\n```\n"
                        "请先 read_gamecenter_project_file 获取精确文本后再 patch。"
                    ),
                }
            count = current.content.count(old_text)
            if count > 1 and not replace_all:
                return {
                    "ok": False,
                    "error": f"old_text matches {count} times",
                    "content": (
                        f"❌ old_text 在文件中出现 {count} 次；请设 replace_all=true 或提供更精确的 old_text。"
                    ),
                }
            limit = -1 if replace_all else 1
            content_arg = current.content.replace(old_text, new_text, limit)

        if not content_arg.strip():
            return {
                "ok": False,
                "error": "empty patch content",
                "content": "❌ 未提供有效内容：请传 content，或 old_text+new_text。",
            }

        try:
            result = service.patch_file(
                slug,
                path,
                content=content_arg,
                actor_user_id=user_id,
                summary=str(args.get("summary") or "") or None,
            )
        except HTTPException as exc:
            detail = str(exc.detail)
            return {
                "ok": False,
                "error": detail,
                "content": (
                    f"❌ 写入失败: {detail}\n"
                    "提示: path 必须是相对工程根目录的路径，例如 `assets/scripts/ui/UIMain.ts`；"
                    "先 list/read 确认文件存在，不要带 slug 前缀。"
                ),
            }

        if result.get("unchanged"):
            return {
                "ok": False,
                "unchanged": True,
                "error": "提交内容与磁盘一致，未写入",
                "content": _fmt_patch_result(result),
                "path": result.get("path"),
            }

        verify_snippet = ""
        try:
            read_back = service.read_file(slug, str(result.get("path") or path))
            actual_sha = hashlib.sha256(read_back.content.encode("utf-8")).hexdigest()
            expected_sha = str(result.get("after_sha256") or "")
            if expected_sha and actual_sha != expected_sha:
                return {
                    "ok": False,
                    "error": "写入后磁盘校验失败",
                    "content": (
                        f"❌ `{result.get('path')}` 写入后校验失败（sha 不一致），请重试或检查磁盘权限。"
                    ),
                    **result,
                }
            verify_snippet = _patch_verify_snippet(
                read_back.content,
                old_text=old_text,
                new_text=new_text,
            )
        except HTTPException as exc:
            return {
                "ok": False,
                "error": f"写入后回读失败: {exc.detail}",
                "content": f"❌ 已写入但回读校验失败: {exc.detail}",
                **result,
            }

        content = _fmt_patch_result(result, verify_snippet=verify_snippet)
        auto_build: dict[str, Any] | None = None
        auto_build = _try_auto_build_after_patch(
            service,
            slug=slug,
            user_id=user_id,
            summary=str(args.get("summary") or "") or None,
        )
        if auto_build:
            if auto_build.get("error"):
                content += f"\n\n⚠️ 自动编译失败：{auto_build['error']}"
            elif auto_build.get("ok"):
                content += "\n\n" + _fmt_build(auto_build)

        # auto git commit when enabled
        slug = str(args.get("slug") or "")
        cfg = _gc_settings()
        if cfg.get("git_auto_commit"):
            try:
                git_result = service.git_commit(slug, (str(args.get("summary") or "") or f"Update {result.get('path', '?')}"))
                if git_result.get("commit"):
                    content += f"\n📝 已自动提交: `{git_result['commit']}`"
            except Exception:
                pass

        return {
            "ok": True,
            "content": content,
            "modified_path": result.get("path"),
            "verified": True,
            "auto_build": auto_build,
            **result,
        }
    if name == "build_gamecenter_project":
        result = service.build_project(
            str(args.get("slug") or ""),
            actor_user_id=user_id,
            summary=str(args.get("summary") or "") or None,
        )
        result["play_urls"] = _play_urls_for_slug(str(args.get("slug") or ""), service=service)
        return {"ok": True, "content": _fmt_build(result), **result}
    if name == "get_gamecenter_build_progress":
        slug = str(args.get("slug") or "")
        progress = service.get_build_progress(slug)
        project = progress.get("project") or _json_dump(service.get_project(slug))
        builds = progress.get("builds") or service.list_builds(slug)
        changes = progress.get("changes") or service.list_changes(slug)
        play_urls = progress.get("play_urls") or _play_urls_for_slug(slug, service=service)
        content = _fmt_build_progress(
            slug,
            project=project,
            builds=builds,
            changes=changes,
            stdout_tail=str(progress.get("stdout_tail") or ""),
            stderr_tail=str(progress.get("stderr_tail") or ""),
            play_urls=play_urls,
        )
        return {
            "ok": True,
            "content": content,
            "project": project,
            "builds": builds,
            "changes": changes[:5],
            "play_urls": play_urls,
            **{k: v for k, v in progress.items() if k not in {"project", "builds", "changes", "play_urls"}},
        }
    if name == "list_gamecenter_project_changes":
        changes = service.list_changes(str(args.get("slug") or ""))
        return {"ok": True, "content": _fmt_changes(changes), "changes": changes}
    if name == "revert_gamecenter_project_change":
        result = service.revert_change(
            str(args.get("slug") or ""),
            str(args.get("change_id") or ""),
            actor_user_id=user_id,
        )
        return {"ok": True, **result}
    if name == "list_gamecenter_project_builds":
        slug = str(args.get("slug") or "")
        project = _json_dump(service.get_project(slug))
        builds = service.list_builds(slug)
        changes = service.list_changes(slug)
        content = _fmt_build_progress(
            slug,
            project=project,
            builds=builds,
            changes=changes,
            play_urls=_play_urls_for_slug(slug, service=service),
        )
        return {"ok": True, "content": content, "builds": builds}
    if name == "publish_gamecenter_project_build":
        result = service.publish_build(
            str(args.get("slug") or ""),
            str(args.get("build_id") or ""),
            actor_user_id=user_id,
            summary=str(args.get("summary") or "") or None,
        )
        play_urls = result.get("play_urls") or []
        content = "发布成功。"
        if play_urls:
            content += " 试玩链接：" + " ".join(play_urls)
        return {"ok": True, "content": content, **result}
    if name == "list_gamecenter_project_releases":
        return {"ok": True, "releases": service.list_releases(str(args.get("slug") or ""))}
    if name == "rollback_gamecenter_project_release":
        result = service.rollback_release(
            str(args.get("slug") or ""),
            str(args.get("release_id") or ""),
            actor_user_id=user_id,
        )
        return {"ok": True, **result}

    # ── new generic devbridge tools ──

    if name == "list_devbridge_projects":
        all_items: list[dict[str, Any]] = []
        provider_keys: list[str] = []
        for provider in _enabled_providers():
            try:
                svc = _resolve_bridge_service(provider.key)
            except HTTPException:
                continue
            for item in svc.list_projects():
                row = item.model_dump()
                row["provider"] = provider.key
                all_items.append(row)
            provider_keys.append(provider.key)
        slugs = [str(item.get("slug") or "") for item in all_items if item.get("slug")]
        preview = ", ".join(slugs[:15])
        if len(slugs) > 15:
            preview += f", …（共 {len(slugs)} 个）"
        return {
            "ok": True,
            "content": (
                f"可访问 {len(all_items)} 个项目"
                + (f"（providers: {', '.join(provider_keys)}）" if provider_keys else "")
                + (f"：{preview}" if preview else "")
            ),
            "projects": all_items,
        }

    if name == "get_devbridge_project_status":
        slug = str(args.get("slug") or "")
        item = service.get_project(slug)
        data = _json_dump(item)
        return {"ok": True, "content": _fmt_project_status(data), "project": data}

    if name == "list_devbridge_project_files":
        slug = str(args.get("slug") or "")
        listing = service.list_files(slug, str(args.get("path") or ""))
        data = _json_dump(listing)
        return {"ok": True, "content": _fmt_file_listing(data), "listing": data}

    if name == "read_devbridge_project_file":
        slug = str(args.get("slug") or "")
        file_data = service.read_file(slug, str(args.get("path") or ""))
        data = _json_dump(file_data)
        return {"ok": True, "content": _fmt_read_file(data), "file": data}

    if name == "patch_devbridge_project_file":
        slug = str(args.get("slug") or "")
        path = str(args.get("path") or "")
        content_arg = str(args.get("content") or "")
        old_text = str(args.get("old_text") or "")
        new_text = str(args.get("new_text") or "")
        replace_all = bool(args.get("replace_all"))
        if old_text or new_text:
            if not old_text or not new_text:
                return {"ok": False, "error": "old_text 与 new_text 必须同时提供", "content": "❌ 局部替换需要同时提供 old_text 和 new_text"}
            if content_arg:
                return {"ok": False, "error": "不能同时使用 content 与 old_text/new_text", "content": "❌ 请二选一"}
            try:
                current = service.read_file(slug, path)
            except HTTPException as exc:
                return {"ok": False, "error": str(exc.detail), "content": f"❌ 读取失败: {exc.detail}"}
            if old_text not in current.content:
                preview = _patch_verify_snippet(current.content, old_text=old_text)
                return {"ok": False, "error": "old_text not found", "content": f"❌ `{current.path}` 中找不到 old_text。磁盘片段:\n```\n{preview}\n```\n请先 read 文件获取精确文本。"}
            count = current.content.count(old_text)
            if count > 1 and not replace_all:
                return {"ok": False, "error": f"old_text matches {count} times", "content": f"❌ old_text 出现 {count} 次，设 replace_all=true 或提供更精确的 old_text"}
            content_arg = current.content.replace(old_text, new_text, -1 if replace_all else 1)
        if not content_arg.strip():
            return {"ok": False, "error": "empty patch content", "content": "❌ 未提供有效内容"}
        try:
            result = service.patch_file(slug, path, content=content_arg, actor_user_id=user_id, summary=str(args.get("summary") or "") or None)
        except HTTPException as exc:
            return {"ok": False, "error": str(exc.detail), "content": f"❌ 写入失败: {exc.detail}"}
        if result.get("unchanged"):
            return {"ok": False, "unchanged": True, "error": "提交内容与磁盘一致", "content": _fmt_patch_result(result), "path": result.get("path")}
        verify_snippet = ""
        try:
            read_back = service.read_file(slug, str(result.get("path") or path))
            vs = _patch_verify_snippet(read_back.content, old_text=old_text, new_text=new_text)
            verify_snippet = vs
        except Exception:
            pass
        content = _fmt_patch_result(result, verify_snippet=verify_snippet)

        # auto git commit when enabled
        cfg = _gc_settings()
        if cfg.get("git_auto_commit"):
            try:
                git_result = service.git_commit(slug, (str(args.get("summary") or "") or f"Update {result.get('path', path)}"))
                if git_result.get("commit"):
                    content += f"\n📝 已自动提交: `{git_result['commit']}`"
            except Exception:
                pass

        return {"ok": True, "content": content, "modified_path": result.get("path"), **result}

    if name == "build_devbridge_project":
        result = service.build_project(str(args.get("slug") or ""), actor_user_id=user_id, summary=str(args.get("summary") or "") or None)
        result["play_urls"] = _play_urls_for_slug(str(args.get("slug") or ""), service=service)
        return {"ok": True, "content": _fmt_build(result), **result}

    if name == "search_devbridge_project_files":
        slug = str(args.get("slug") or "")
        pattern = str(args.get("pattern") or "")
        if not pattern:
            return {"ok": False, "error": "pattern is required", "content": "❌ 搜索模式不能为空"}
        result = service.search_files(
            slug,
            pattern,
            path_hint=str(args.get("path") or ""),
        )
        content_lines = [f"🔍 `{slug}` 搜索结果: `{pattern}` — 匹配 {result['matches']} 条（扫描 {result['scanned_files']} 个文件）"]
        for r in result.get("results", [])[:15]:
            content_lines.append(f"- `{r['file']}:{r['line']}` {r['text']}")
        if result.get("truncated"):
            content_lines.append(f"…（结果已截断，如需更精确请缩小搜索范围）")
        return {"ok": True, "content": "\n".join(content_lines), **result}

    if name == "diff_devbridge_project_change":
        slug = str(args.get("slug") or "")
        change_id = str(args.get("change_id") or "")
        try:
            result = service.diff_change(slug, change_id)
        except HTTPException as exc:
            return {"ok": False, "error": str(exc.detail), "content": f"❌ {exc.detail}"}
        content = f"📋 变更 `{change_id}`"
        if result.get("metadata"):
            m = result["metadata"]
            content += f"\n- 文件: `{m.get('path', '?')}` — {m.get('actor_user_id', '?')} @ {m.get('created_at', '?')}"
        if result.get("lines_changed"):
            content += f"\n- 变更 {result['lines_changed']} 行"
        if result.get("diff"):
            content += f"\n```diff\n{result['diff']}\n```"
        return {"ok": True, "content": content, **result}

    if name == "list_devbridge_templates":
        templates = service._TEMPLATES
        items = ", ".join(f"{k}（{v['description']}）" for k, v in sorted(templates.items()))
        return {"ok": True, "content": f"可用项目模板: {items}", "templates": templates}

    if name == "create_devbridge_project":
        slug = str(args.get("slug") or "")
        template = str(args.get("template") or "")
        provider_key = str(args.get("provider") or "gamecenter").strip().lower()
        try:
            project_service = _resolve_bridge_service(provider_key)
            result = project_service.create_project(slug, template)
        except HTTPException as exc:
            return {"ok": False, "error": str(exc.detail), "content": f"❌ {exc.detail}"}
        # Auto-add to group allowlist if running in group context
        conv = get_bot_conversation()
        if conv and conv.scope_type == "group" and conv.scope_id:
            try:
                db = get_bot_db()
                if db:
                    from sqlalchemy import select
                    from app.models.group import Group
                    group = (await db.execute(select(Group).where(Group.id == conv.scope_id))).scalar_one_or_none()
                    if group:
                        allowlists = dict(group.devbridge_project_allowlists or {})
                        provider_list = list(allowlists.get(provider_key) or [])
                        if slug not in provider_list:
                            provider_list.append(slug)
                            allowlists[provider_key] = provider_list
                            group.devbridge_project_allowlists = allowlists
                            await db.commit()
            except Exception:
                pass
        files = result.get("created_files", [])
        play_urls = _play_urls_for_slug(slug, service=project_service)
        content = f"✅ 项目 `{result['slug']}` 已创建（{result['template_description']}）\n- 模板: {result['template']}\n- 路径: `{result['project_dir']}`\n- 已自动加入管理列表"
        if play_urls:
            content += f"\n- 试玩地址: {play_urls[0]}"
        content += "\n- 生成文件:\n  " + "\n  ".join(f"• `{f}`" for f in files)
        return {"ok": True, "content": content, "play_urls": play_urls, **result}

    if name == "upload_devbridge_asset":
        slug = str(args.get("slug") or "")
        path = str(args.get("path") or "")
        data_b64 = str(args.get("data") or "")
        overwrite = bool(args.get("overwrite"))
        try:
            result = service.upload_asset(slug, path, data_b64, overwrite=overwrite)
        except HTTPException as exc:
            return {"ok": False, "error": str(exc.detail), "content": f"❌ {exc.detail}"}
        size_kb = result["size_bytes"] / 1024
        content = f"✅ 资源已上传 `{result['path']}` — {size_kb:.1f} KB"
        if result.get("overwritten"):
            content += "（已覆盖）"
        return {"ok": True, "content": content, **result}

    # ── git tools ──

    if name == "git_status_devbridge_project":
        slug = str(args.get("slug") or "")
        result = service.git_status(slug)
        if not result.get("initialized"):
            return {"ok": True, "content": f"📂 `{slug}` 尚未初始化 git。用 git_init_devbridge_project 来启用版本管理。", **result}
        changes = result.get("files", [])
        lines = [f"📂 `{slug}` git 状态"]
        if changes:
            for f in changes[:20]:
                lines.append(f"  {f['status']:>2} {f['file']}")
            if len(changes) > 20:
                lines.append(f"  … 共 {len(changes)} 项变更")
        else:
            lines.append("  ✅ 工作区干净")
        if result.get("has_remote"):
            lines.append("  🌐 已配置远程仓库")
        return {"ok": True, "content": "\n".join(lines), **result}

    if name == "git_log_devbridge_project":
        slug = str(args.get("slug") or "")
        result = service.git_log(slug)
        if not result.get("initialized"):
            return {"ok": True, "content": f"📂 `{slug}` 尚未初始化 git。", **result}
        commits = result.get("commits", [])
        lines = [f"📂 `{slug}` 最近提交:"]
        for c in commits[:15]:
            lines.append(f"  {c}")
        if len(commits) > 15:
            lines.append(f"  … 共 {len(commits)} 条")
        return {"ok": True, "content": "\n".join(lines), **result}

    if name == "git_init_devbridge_project":
        slug = str(args.get("slug") or "")
        try:
            result = service.git_init(slug)
        except HTTPException as exc:
            return {"ok": False, "error": str(exc.detail), "content": f"❌ {exc.detail}"}
        return {"ok": True, "content": f"✅ `{slug}` git 仓库已初始化（含 .gitignore、初始提交）", **result}

    if name == "git_commit_devbridge_project":
        slug = str(args.get("slug") or "")
        message = str(args.get("message") or "Update via DevBridge")
        try:
            result = service.git_commit(slug, message)
        except HTTPException as exc:
            return {"ok": False, "error": str(exc.detail), "content": f"❌ {exc.detail}"}
        if result.get("status") == "nothing_to_commit":
            return {"ok": True, "content": f"📂 `{slug}` 没有需要提交的变更，工作区已是最新。", **result}
        return {"ok": True, "content": f"✅ `{slug}` 已提交: `{result.get('commit', '')}`", **result}

    if name == "git_set_remote_devbridge_project":
        slug = str(args.get("slug") or "")
        remote_url = str(args.get("remote_url") or "")
        try:
            result = service.git_set_remote(slug, remote_url)
        except HTTPException as exc:
            return {"ok": False, "error": str(exc.detail), "content": f"❌ {exc.detail}"}
        return {"ok": True, "content": f"✅ `{slug}` 远程仓库已设为 `{result['remote_url']}`", **result}

    if name == "git_push_devbridge_project":
        slug = str(args.get("slug") or "")
        try:
            result = service.git_push(slug)
        except HTTPException as exc:
            return {"ok": False, "error": str(exc.detail), "content": f"❌ {exc.detail}"}
        return {"ok": True, "content": f"✅ `{slug}` 已推送到远程仓库", **result}

    return None


_GAMECENTER_EXTENSIONS_REGISTERED = False


def register_gamecenter_bridge_extensions() -> None:
    global _GAMECENTER_EXTENSIONS_REGISTERED
    if _GAMECENTER_EXTENSIONS_REGISTERED:
        return
    _GAMECENTER_EXTENSIONS_REGISTERED = True

    prev_extra = chat_extensions._handlers["extra_tools"]
    prev_augment = chat_extensions._handlers["augment_system_prompt"]
    prev_execute = chat_extensions._handlers["execute_tool"]

    def merged_extra(conversation: Conversation, ctx: Any) -> list[dict[str, Any]]:
        tools = list(prev_extra(conversation, ctx))
        tools.extend(_extra_tools(conversation, ctx))
        return tools

    def merged_augment(conversation: Conversation, ctx: Any, prompt: str) -> str:
        next_prompt = _hint(prompt) if conversation_allows_bridge(conversation) else prompt
        return prev_augment(conversation, ctx, next_prompt)

    async def merged_execute(name: str, args: dict[str, Any], ctx: Any) -> Any | None:
        result = await _execute(name, args, ctx)
        if result is not None:
            return result
        prev_result = prev_execute(name, args, ctx)
        if prev_result is not None and hasattr(prev_result, "__await__"):
            return await prev_result
        return prev_result

    chat_extensions.register_chat_extensions(
        extra_tools=merged_extra,
        augment_system_prompt=merged_augment,
        execute_tool=merged_execute,
    )
