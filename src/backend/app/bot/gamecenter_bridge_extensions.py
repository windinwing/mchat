"""GameCenter bridge tools for internal chat."""

from __future__ import annotations

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


def _fmt_patch_result(data: dict[str, Any]) -> str:
    if data.get("unchanged"):
        return f"ℹ️ `{data.get('path')}` 无变化（磁盘内容与提交一致，未写入）"
    summary = (data.get("summary") or "").strip()
    extra = f" — {summary}" if summary else ""
    change_id = (data.get("id") or "").strip()
    after_sha = (data.get("after_sha256") or "")[:12]
    verify = ""
    if change_id:
        verify = (
            f"\n- 变更记录 id: `{change_id}`（可用 list_gamecenter_project_changes 核对）"
            f"\n- after_sha256: `{after_sha}…`"
        )
    return f"✏️ 已写入服务器 `{data.get('path')}`{extra}{verify}"


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


def _fmt_build(data: dict[str, Any]) -> str:
    status = str(data.get("status") or "unknown")
    build_id = str(data.get("id") or "")
    cmd = str(data.get("command") or "")
    lines = [f"🔨 构建 {status}" + (f" · `{build_id}`" if build_id else "")]
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


def _play_urls_for_slug(slug: str) -> list[str]:
    cfg = _gc_settings()
    bases = [str(item).strip() for item in (cfg.get("playable_base_urls") or []) if str(item).strip()]
    if not bases and cfg.get("playable_base_url"):
        bases = [str(cfg.get("playable_base_url")).strip()]
    return [f"{base.rstrip('/')}/{slug}/" for base in bases]


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
        result["play_urls"] = _play_urls_for_slug(slug)
        return result
    except HTTPException as exc:
        return {"error": str(exc.detail)}

from fastapi import HTTPException

from app.bot import chat_extensions
from app.bot.tool_runtime import get_bot_conversation, get_bot_db, get_bot_user_id
from app.core.config import settings
from app.models.conversation import Conversation
from app.services.devbridge_admin_settings import resolved_gamecenter_settings
from app.models.user import User
from app.services.gamecenter_provider import create_gamecenter_bridge_service

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
            "description": "Write a controlled UTF-8 text file inside a GameCenter project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["slug", "path", "content"],
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
    {
        "type": "function",
        "function": {
            "name": "list_gamecenter_project_builds",
            "description": "List recent build records for a GameCenter project.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
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

_ALL_TOOL_NAMES = {
    tool["function"]["name"]
    for tool in _READ_TOOLS + _WRITE_TOOLS + _PUBLISH_TOOLS
}


def _hint(prompt: str) -> str:
    extra = (
        "\n\nWhen the user asks about internal GameCenter projects, code layout, readable files, or build status, "
        "use the gamecenter bridge tools before answering."
    )
    cfg = resolved_gamecenter_settings()
    if settings.gamecenter_bridge_write_enabled:
        extra += " For controlled edits, use patch/build/change tools instead of inventing shell commands."
        if cfg.get("auto_build_after_patch"):
            extra += (
                " After a successful patch, the system auto-runs build_command on the configured Mac/Windows builder; "
                "do not claim build/publish success unless the auto-build result is shown. "
                ":5099 playable is updated via build/web-mobile push — publish is optional."
            )
        else:
            extra += (
                " After patching source files, you MUST call build_gamecenter_project (real remote build), "
                "then tell the user to hard-refresh the playable URL. Never skip build or fake success."
            )
    if settings.gamecenter_publish_enabled:
        extra += " Publishing to playables is optional when build_command already pushes build/web-mobile."
    return prompt + extra


def _gc_settings() -> dict:
    return resolved_gamecenter_settings()


async def _staff_allowed(conversation: Conversation | None = None) -> bool:
    db = get_bot_db()
    user_id = get_bot_user_id()
    if db is None or not user_id or not _gc_settings().get("enabled"):
        return False
    if conversation is not None and not _conversation_allows_bridge(conversation):
        return False
    user = await db.get(User, user_id)
    return bool(user and user.role in {"admin", "agent"})


def _conversation_allows_bridge(conversation: Conversation) -> bool:
    cfg = _gc_settings()
    if not cfg.get("enabled"):
        return False
    if cfg.get("bridge_group_scope_only", True):
        return conversation.scope_type == "group"
    return True


def _extra_tools(conversation: Conversation, _ctx: Any) -> list[dict[str, Any]]:
    if not conversation.user_id or not _conversation_allows_bridge(conversation):
        return []
    tools = list(_READ_TOOLS)
    cfg = _gc_settings()
    if cfg.get("write_enabled"):
        tools.extend(_WRITE_TOOLS)
    if cfg.get("publish_enabled"):
        tools.extend(_PUBLISH_TOOLS)
    return tools


async def _execute(name: str, args: dict[str, Any], _ctx: Any) -> Any | None:
    if name not in _ALL_TOOL_NAMES:
        return None
    if not await _staff_allowed(get_bot_conversation()):
        return {"error": "GameCenter bridge not available for current user"}

    service = create_gamecenter_bridge_service()
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
        try:
            result = service.patch_file(
                str(args.get("slug") or ""),
                str(args.get("path") or ""),
                content=str(args.get("content") or ""),
                actor_user_id=user_id,
                summary=str(args.get("summary") or "") or None,
            )
        except HTTPException as exc:
            detail = str(exc.detail)
            return {
                "error": detail,
                "content": (
                    f"❌ 写入失败: {detail}\n"
                    "提示: path 必须是相对工程根目录的路径，例如 `assets/scripts/game/Stage.ts`；"
                    "先 list/read 确认文件存在，不要带 slug 前缀。"
                ),
            }
        content = _fmt_patch_result(result)
        auto_build: dict[str, Any] | None = None
        if result.get("ok") and not result.get("unchanged"):
            auto_build = _try_auto_build_after_patch(
                service,
                slug=str(args.get("slug") or ""),
                user_id=user_id,
                summary=str(args.get("summary") or "") or None,
            )
            if auto_build:
                if auto_build.get("error"):
                    content += f"\n\n⚠️ 自动编译失败：{auto_build['error']}"
                elif auto_build.get("ok"):
                    content += "\n\n" + _fmt_build(auto_build)
        return {
            "ok": True,
            "content": content,
            "modified_path": result.get("path"),
            "auto_build": auto_build,
            **result,
        }
    if name == "build_gamecenter_project":
        result = service.build_project(
            str(args.get("slug") or ""),
            actor_user_id=user_id,
            summary=str(args.get("summary") or "") or None,
        )
        result["play_urls"] = _play_urls_for_slug(str(args.get("slug") or ""))
        return {"ok": True, "content": _fmt_build(result), **result}
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
        return {"ok": True, "builds": service.list_builds(str(args.get("slug") or ""))}
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
    return None


def register_gamecenter_bridge_extensions() -> None:
    prev_extra = chat_extensions._handlers["extra_tools"]
    prev_augment = chat_extensions._handlers["augment_system_prompt"]
    prev_execute = chat_extensions._handlers["execute_tool"]

    def merged_extra(conversation: Conversation, ctx: Any) -> list[dict[str, Any]]:
        tools = list(prev_extra(conversation, ctx))
        tools.extend(_extra_tools(conversation, ctx))
        return tools

    def merged_augment(conversation: Conversation, ctx: Any, prompt: str) -> str:
        next_prompt = _hint(prompt) if _conversation_allows_bridge(conversation) else prompt
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
