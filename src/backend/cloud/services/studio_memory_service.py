"""OpenClaw-style Markdown workspace memory for Cloud Portal studio chat."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from cloud.config import cloud_settings
from cloud.services.studio_memory_index import (
    MemorySearchHit,
    StudioMemoryIndex,
    schedule_index_sync,
)
from cloud.utils.studio_paths import resolve_studio_workspace_root, safe_workspace_segment


@dataclass
class StudioMemoryBootstrap:
    memory_md: str
    daily_notes: list[tuple[str, str]]


def is_studio_chat(conversation) -> bool:
    """Portal studio chat: authenticated user bound to a subscribed channel."""
    return bool(getattr(conversation, "user_id", None)) and bool(
        getattr(conversation, "customer_id", None)
    )


class StudioMemoryService:
    """Read/write per-user per-channel Markdown memory workspace."""

    MEMORY_FILE = "MEMORY.md"
    DAILY_DIR = "memory"

    def __init__(self, user_id: str, channel_id: str) -> None:
        uid = safe_workspace_segment(user_id)
        cid = safe_workspace_segment(channel_id)
        if not uid or not cid:
            raise ValueError("Invalid studio memory workspace identifiers")
        self.user_id = uid
        self.channel_id = cid
        self.workspace = resolve_studio_workspace_root() / uid / cid

    @classmethod
    def for_conversation(cls, conversation) -> StudioMemoryService | None:
        if not is_studio_chat(conversation):
            return None
        return cls(str(conversation.user_id), str(conversation.customer_id))

    def _today_key(self) -> str:
        tz_name = cloud_settings.studio_memory_timezone or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = timezone.utc
        return datetime.now(tz).strftime("%Y-%m-%d")

    def ensure_workspace(self) -> Path:
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / self.DAILY_DIR).mkdir(parents=True, exist_ok=True)
        memory_path = self.workspace / self.MEMORY_FILE
        if not memory_path.exists():
            memory_path.write_text("", encoding="utf-8")
        return self.workspace

    def memory_path(self) -> Path:
        return self.ensure_workspace() / self.MEMORY_FILE

    def daily_path(self, date_key: str | None = None) -> Path:
        key = (date_key or self._today_key()).strip()
        if not key or "/" in key or ".." in key:
            raise ValueError("Invalid daily memory date")
        return self.ensure_workspace() / self.DAILY_DIR / f"{key}.md"

    def read_memory_file(self) -> str:
        path = self.memory_path()
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def write_memory_file(self, content: str, *, mode: str = "replace") -> None:
        path = self.memory_path()
        if mode == "append":
            existing = path.read_text(encoding="utf-8") if path.is_file() else ""
            sep = "\n\n" if existing.strip() else ""
            path.write_text(existing.rstrip() + sep + content.strip() + "\n", encoding="utf-8")
        else:
            path.write_text(content.rstrip() + "\n", encoding="utf-8")
        schedule_index_sync(self.workspace)

    def read_daily_file(self, date_key: str) -> str:
        path = self.daily_path(date_key)
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def write_daily_file(
        self,
        content: str,
        *,
        date_key: str | None = None,
        mode: str = "append",
    ) -> str:
        path = self.daily_path(date_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "replace":
            path.write_text(content.rstrip() + "\n", encoding="utf-8")
        else:
            existing = path.read_text(encoding="utf-8") if path.is_file() else ""
            sep = "\n\n" if existing.strip() else ""
            path.write_text(existing.rstrip() + sep + content.strip() + "\n", encoding="utf-8")
        schedule_index_sync(self.workspace)
        return path.name

    def append_daily_turn(
        self,
        user_text: str,
        assistant_text: str,
        *,
        conversation_id: str | None = None,
    ) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = f"### Turn {stamp}"
        if conversation_id:
            header += f" (`{conversation_id[:8]}`)"
        block = (
            f"{header}\n\n"
            f"**User:**\n{user_text.strip()}\n\n"
            f"**Assistant:**\n{assistant_text.strip()}"
        )
        self.write_daily_file(block, mode="append")

    def append_session_reset(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.write_daily_file(f"## Session reset ({stamp})\n", mode="append")

    def list_daily_dates(self, *, limit: int = 14) -> list[str]:
        daily_dir = self.ensure_workspace() / self.DAILY_DIR
        dates = sorted(
            (p.stem for p in daily_dir.glob("*.md")),
            reverse=True,
        )
        return dates[:limit]

    def read_bootstrap(self) -> StudioMemoryBootstrap:
        self.ensure_workspace()
        memory_md = self.read_memory_file().strip()
        max_chars = max(
            500, int(cloud_settings.studio_memory_bootstrap_max_chars or 8000)
        )
        if len(memory_md) > max_chars:
            memory_md = memory_md[:max_chars] + "\n\n…(truncated for prompt budget)"

        days = max(1, int(cloud_settings.studio_memory_daily_bootstrap_days or 2))
        tz_name = cloud_settings.studio_memory_timezone or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = timezone.utc
        today = datetime.now(tz).date()
        daily_notes: list[tuple[str, str]] = []
        remaining = max_chars
        for offset in range(days):
            date_key = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
            text = self.read_daily_file(date_key).strip()
            if not text:
                continue
            if len(text) > remaining:
                text = text[-remaining:]
                text = "…(truncated)\n" + text
            daily_notes.append((date_key, text))
            remaining = max(0, remaining - len(text))
            if remaining <= 0:
                break
        return StudioMemoryBootstrap(memory_md=memory_md, daily_notes=daily_notes)

    def search(self, query: str, *, top_k: int = 5) -> list[MemorySearchHit]:
        return StudioMemoryIndex(self.ensure_workspace()).search(query, top_k=top_k)

    def get_file_slice(
        self,
        path: str,
        *,
        line_start: int | None = None,
        line_end: int | None = None,
    ) -> dict[str, Any]:
        rel = (path or "").strip().lstrip("/")
        if not rel or ".." in rel.split("/"):
            return {"error": "Invalid path"}
        if rel != self.MEMORY_FILE and not (
            rel.startswith(f"{self.DAILY_DIR}/") and rel.endswith(".md")
        ):
            return {"error": "Path not allowed"}
        full = (self.workspace / rel).resolve()
        try:
            full.relative_to(self.workspace.resolve())
        except ValueError:
            return {"error": "Path traversal denied"}
        if not full.is_file():
            return {"error": "File not found", "path": rel}
        lines = full.read_text(encoding="utf-8").splitlines()
        start = max(1, int(line_start or 1))
        end = min(len(lines), int(line_end or len(lines)))
        if end < start:
            end = start
        snippet = "\n".join(lines[start - 1 : end])
        return {
            "path": rel,
            "line_start": start,
            "line_end": end,
            "content": snippet,
        }


def format_studio_memory_section(bootstrap: StudioMemoryBootstrap) -> str:
    if not bootstrap.memory_md and not bootstrap.daily_notes:
        return (
            "\n\n## Studio Memory (local Markdown workspace)\n"
            "No saved memory yet. Use studio_memory_write to persist durable facts in MEMORY.md.\n"
        )
    parts = ["\n\n## Studio Memory (local Markdown workspace)"]
    parts.append("### Long-term (MEMORY.md)")
    parts.append(bootstrap.memory_md or "_(empty)_")
    if bootstrap.daily_notes:
        parts.append("### Recent daily notes")
        for date_key, text in bootstrap.daily_notes:
            parts.append(f"#### {date_key}")
            parts.append(text)
    return "\n".join(parts) + "\n"


STUDIO_MEMORY_TOOL_HINT = (
    "\n\n## Studio memory tools\n"
    "- studio_memory_write: save durable facts to MEMORY.md or append details to today's daily log\n"
    "- studio_memory_search: keyword search across MEMORY.md and memory/*.md\n"
    "- studio_memory_get: read a slice of MEMORY.md or memory/YYYY-MM-DD.md\n"
    "Keep MEMORY.md concise (preferences, decisions, project facts). Put verbose context in daily logs.\n"
    "When the user asks you to remember something, call studio_memory_write.\n"
)


STUDIO_MEMORY_OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "studio_memory_write",
            "description": "Write to the local Markdown memory workspace (MEMORY.md or daily log).",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["memory", "daily"],
                        "description": "memory=MEMORY.md long-term; daily=today's log",
                    },
                    "content": {"type": "string", "description": "Markdown content to save"},
                    "mode": {
                        "type": "string",
                        "enum": ["append", "replace"],
                        "description": "append (default) or replace entire file",
                    },
                },
                "required": ["target", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "studio_memory_search",
            "description": "Search Markdown memory files by keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "description": "Max results, default 5"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "studio_memory_get",
            "description": "Read a slice of a memory Markdown file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "MEMORY.md or memory/YYYY-MM-DD.md",
                    },
                    "line_start": {"type": "integer"},
                    "line_end": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
]


def execute_studio_memory_tool(
    service: StudioMemoryService,
    tool_name: str,
    tool_args: dict[str, Any],
) -> dict[str, Any]:
    if tool_name == "studio_memory_write":
        target = str(tool_args.get("target") or "memory").lower()
        content = str(tool_args.get("content") or "").strip()
        mode = str(tool_args.get("mode") or "append").lower()
        if not content:
            return {"error": "content is required"}
        if target == "daily":
            filename = service.write_daily_file(content, mode=mode)
            return {"ok": True, "path": f"memory/{filename}", "mode": mode}
        service.write_memory_file(content, mode=mode)
        return {"ok": True, "path": "MEMORY.md", "mode": mode}

    if tool_name == "studio_memory_search":
        query = str(tool_args.get("query") or "").strip()
        top_k = int(tool_args.get("top_k") or 5)
        hits = service.search(query, top_k=max(1, min(top_k, 10)))
        return {
            "ok": True,
            "query": query,
            "results": [
                {
                    "path": h.path,
                    "line_start": h.line_start,
                    "line_end": h.line_end,
                    "score": h.score,
                    "snippet": h.content,
                }
                for h in hits
            ],
        }

    if tool_name == "studio_memory_get":
        return service.get_file_slice(
            str(tool_args.get("path") or ""),
            line_start=tool_args.get("line_start"),
            line_end=tool_args.get("line_end"),
        )

    return {"error": f"Unknown studio memory tool: {tool_name}"}
