"""Resolve skills and knowledge scope for a chat turn."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import copy

from app.models.customer import CustomerConfig
from app.models.skill import Skill
from app.services.field_encryption import decrypt_skill_bindings
from app.core.config import settings
from app.skill.ops_policy import (
    filter_skills_by_ops_policy,
    notification_enabled_for_user,
    server_ops_enabled_for_user,
)
from app.skill.utils import get_prompt_body, has_executable_script
from app.bot.patent_search_followup import append_patent_tool_hints as _append_patent_tool_hints


def _merge_channel_skill_bindings(
    skills: list[Skill],
    customer_config: CustomerConfig | None,
) -> list[Skill]:
    """Overlay per-channel skill_bindings onto skill.config (e.g. earth2037 game_api_key)."""
    if customer_config is None:
        return skills
    bindings = decrypt_skill_bindings(
        getattr(customer_config, "skill_bindings", None) or {}
    )
    if not isinstance(bindings, dict) or not bindings:
        return skills

    merged: list[Skill] = []
    for skill in skills:
        binding = bindings.get(skill.name)
        if not isinstance(binding, dict):
            merged.append(skill)
            continue
        if not binding.get("override", False):
            merged.append(skill)
            continue
        cfg = copy.deepcopy(skill.config or {})
        channel_secrets = binding.get("secrets") or binding.get("env") or {}
        if isinstance(channel_secrets, dict) and channel_secrets:
            base_secrets = dict(cfg.get("secrets") or cfg.get("env") or {})
            base_secrets.update(channel_secrets)
            cfg["secrets"] = base_secrets
        for key, value in binding.items():
            if key in ("secrets", "env", "override"):
                continue
            if isinstance(value, (dict, list)):
                continue
            cfg[key] = value
        clone = Skill(
            id=skill.id,
            user_id=skill.user_id,
            name=skill.name,
            description=skill.description,
            skill_type=skill.skill_type,
            path=skill.path,
            config=cfg,
            enabled=skill.enabled,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
        )
        merged.append(clone)
    return merged


def _ids_from_config(value: list[str] | None) -> list[str] | None:
    """None/[] = use none; non-empty = filter to those ids."""
    if value is None:
        return []
    cleaned = [str(x).strip() for x in value if str(x).strip()]
    return cleaned


async def load_skills_for_chat(
    db: AsyncSession,
    user_id: str,
    customer_config: CustomerConfig | None = None,
    skill_ids_override: list[str] | None = None,
) -> tuple[list[Skill], list[Skill]]:
    """Return (prompt_skills, executable_tool_skills) for this chat."""
    result = await db.execute(
        select(Skill).where(
            Skill.user_id == user_id,
            Skill.enabled == True,
        )
    )
    all_skills = list(result.scalars().all())

    allowed_ids = None
    if skill_ids_override is not None:
        allowed_ids = _ids_from_config(skill_ids_override)
    elif customer_config is not None:
        allowed_ids = _ids_from_config(
            getattr(customer_config, "skill_ids", None)
        )

    if allowed_ids is not None:
        if len(allowed_ids) == 0:
            return [], []
        allowed_set = set(allowed_ids)
        all_skills = [s for s in all_skills if s.id in allowed_set]

    # Never expose server_ops tools on widget / portal / multi-tenant channels.
    allow_server_ops = await server_ops_enabled_for_user(db, user_id)
    allow_notification = await notification_enabled_for_user(db, user_id)
    if customer_config is not None:
        allow_server_ops = False
        allow_notification = False
    allowlist = getattr(settings, "server_ops_skill_allowlist", None)
    notification_allowlist = getattr(settings, "notification_skill_allowlist", None)
    all_skills = filter_skills_by_ops_policy(
        all_skills,
        allow_server_ops=allow_server_ops,
        allowlist=allowlist,
        allow_notification=allow_notification,
        notification_allowlist=notification_allowlist,
    )

    all_skills = _merge_channel_skill_bindings(all_skills, customer_config)

    prompt_skills: list[Skill] = []
    tool_skills: list[Skill] = []

    for skill in all_skills:
        skill_type = (skill.skill_type or "tool").lower()
        executable = has_executable_script(skill.path)

        if skill_type == "webhook":
            tool_skills.append(skill)
            continue

        if skill_type == "prompt" or (skill_type == "tool" and not executable):
            if get_prompt_body(skill):
                prompt_skills.append(skill)
            continue

        if skill_type in ("tool", "function") and executable:
            tool_skills.append(skill)

    return prompt_skills, tool_skills


# Keep system prompt lean — full SKILL.md can be 10k+ chars per skill.
_MAX_PROMPT_SKILL_CHARS = 1500

# Default OpenAI tool schemas for known skills (when SKILL.md has no parameters).
_DEFAULT_TOOL_PARAMETERS: dict[str, dict[str, Any]] = {
    "patent-search": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": [
                    "search",
                    "export",
                    "export_analysis",
                    "detail",
                    "claims",
                    "description",
                    "legal",
                    "citing",
                    "similar",
                    "image",
                    "analysis",
                    "company",
                    "copyright",
                    "trademark",
                    "help",
                ],
                "description": "专利技能子命令；export/export_analysis 导出 Excel",
            },
            "query": {
                "type": "string",
                "description": "检索式/关键词（search、analysis、copyright 等）",
            },
            "patent_id": {
                "type": "string",
                "description": "专利公开号（detail、claims、legal 等）",
            },
            "company_name": {"type": "string", "description": "企业名称（company）"},
            "dimension": {
                "type": "string",
                "enum": [
                    "applicant",
                    "ipc",
                    "applicationYear",
                    "legalStatus",
                    "province",
                ],
                "description": "统计分析维度（command=analysis 时必填）",
            },
            "page": {"type": "integer", "description": "页码"},
            "page_size": {"type": "integer", "description": "每页条数"},
            "scope": {
                "type": "string",
                "enum": ["cn", "us", "jp", "kr", "tw", "wo", "ep", "all"],
                "description": "数据范围：cn、all、us、jp、kr、tw、wo、ep",
            },
            "details": {"type": "boolean", "description": "search 时展示 IPC、摘要等明细列"},
        },
        "required": ["command"],
    },
    "patent-transaction": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": [
                    "search",
                    "export",
                    "export_orders",
                    "detail",
                    "sellers",
                    "orders",
                    "open",
                    "demand",
                    "info",
                ],
                "description": "交易子命令；export 导出在售专利 Excel",
            },
            "query": {
                "type": "string",
                "description": "关键词（search、open、demand）",
            },
            "patent_id": {
                "type": "string",
                "description": "专利申请号（detail、sellers）",
            },
            "page": {"type": "integer", "description": "页码"},
            "page_size": {"type": "integer", "description": "每页条数"},
        },
        "required": ["command"],
    },
    "patent-disclosure": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["export", "template", "checklist"],
                "description": "export=导出 Word（需 content）；template=空白模板；checklist=检查清单",
            },
            "content": {
                "type": "string",
                "description": "完整交底书 Markdown 正文（export 时必填）",
            },
            "invention_name": {
                "type": "string",
                "description": "发明名称，用于 Word 文件名与文档标题",
            },
            "title": {
                "type": "string",
                "description": "同 invention_name，文档标题",
            },
        },
        "required": ["command"],
    },
    "patent-report": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["chart", "excel", "word", "ppt", "all"],
                "description": "chart=PNG 图表；excel/word/ppt=单格式；all=图表+Office 全套",
            },
            "sections": {
                "type": "object",
                "description": "merge 节点 sections（工作流 ${nodes.merge.sections}）",
            },
            "title": {"type": "string", "description": "报告标题"},
            "filename": {
                "type": "string",
                "description": "输出文件名（不含扩展名）",
            },
            "charts": {
                "type": "array",
                "description": "上游 chart 节点 charts（可选 ${nodes.chart.charts}）",
            },
        },
        "required": ["command"],
    },
    "mchat-notify": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["ping", "send", "workflow_alert"],
                "description": "ping=测试；send=自定义内容；workflow_alert=工作流告警模板",
            },
            "phone": {"type": "string", "description": "11 位手机号（须在系统白名单）"},
            "provider": {
                "type": "string",
                "enum": ["dev", "auto"],
                "description": "dev=仅日志；auto=尝试 skills/mchat-notify/providers/ 下已安装插件",
            },
            "content": {"type": "string", "description": "command=send 时的正文（≤500 字）"},
            "workflow_name": {"type": "string"},
            "event": {"type": "string"},
            "run_id": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["command", "phone"],
    },
    "mchat-ops": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": [
                    "health",
                    "logs",
                    "milvus",
                    "k8s",
                    "redis",
                    "disk",
                    "services",
                    "db",
                    "run",
                ],
                "description": "health/logs/milvus/k8s/redis/disk/services/db/run",
            },
            "shell_id": {
                "type": "string",
                "description": "command=run 时：系统设置里配置的白名单命令 id",
            },
            "source": {
                "type": "string",
                "enum": ["app", "error"],
                "description": "logs 时选择 app 或 error 日志",
            },
            "lines": {
                "type": "integer",
                "description": "logs 行数，默认 80，最大 200",
            },
            "namespace": {
                "type": "string",
                "description": "k8s 命名空间，默认 default",
            },
            "resource": {
                "type": "string",
                "enum": ["pods", "nodes", "deployments", "services", "events"],
                "description": "k8s 资源类型（只读 get）",
            },
        },
        "required": ["command"],
    },
}


def build_executable_skill_prompt_section(tool_skills: list[Skill]) -> str:
    """可执行工具技能若含 prompt_body（如 patent-disclosure），注入系统提示。"""
    parts: list[str] = []
    for skill in tool_skills:
        config = skill.config or {}
        body = config.get("prompt_body") or ""
        if not str(body).strip():
            continue
        parts.append(f"### Skill: {skill.name}\n{_truncate_prompt_body(str(body))}")
    if not parts:
        return ""
    return "\n\n## Active Skills (tools with guidance)\n" + "\n\n".join(parts)


def _truncate_prompt_body(body: str) -> str:
    if len(body) <= _MAX_PROMPT_SKILL_CHARS:
        return body
    return (
        body[:_MAX_PROMPT_SKILL_CHARS]
        + "\n\n…(skill guidance truncated; see skill files for full text)"
    )


_MCHAT_OPS_HINT = (
    "\n\n## Tool: mchat-ops\n"
    "- health: DB / Milvus / Redis summary\n"
    "- logs: source=app|error, lines default 80\n"
    "- milvus: vector store runtime status\n"
    "- k8s: read-only kubectl get (namespace, resource=pods|nodes|...)\n"
    "- redis / disk: connectivity and disk usage\n"
    "- services: systemd service status\n"
    "- db: MySQL ping\n"
    "- run: allowlisted shell command (shell_id from Settings → Security)\n"
    "Summarize ops output for the user; do not invent data."
)


def append_patent_tool_hints(
    system_prompt: str, tool_skills: list[Skill]
) -> str:
    system_prompt = _append_patent_tool_hints(system_prompt, tool_skills)
    if any((s.name or "") == "mchat-ops" for s in tool_skills):
        system_prompt += _MCHAT_OPS_HINT
    return system_prompt


def build_prompt_skill_section(prompt_skills: list[Skill]) -> str:
    if not prompt_skills:
        return ""
    parts: list[str] = []
    for skill in prompt_skills:
        desc = (skill.description or "").strip()
        body = get_prompt_body(skill)
        if body and body != desc:
            body = _truncate_prompt_body(body)
        elif desc:
            body = desc
        else:
            continue
        parts.append(f"### Skill: {skill.name}\n{body}")
    if not parts:
        return ""
    return "\n\n## Active Skills\n" + "\n\n".join(parts)


def build_openai_tools(tool_skills: list[Skill]) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for skill in tool_skills:
        config = skill.config or {}
        parameters = config.get("parameters")
        if not parameters or parameters == {"type": "object", "properties": {}}:
            parameters = _DEFAULT_TOOL_PARAMETERS.get(
                skill.name,
                {"type": "object", "properties": {}},
            )
        desc = (skill.description or "").strip()
        if len(desc) > 500:
            desc = desc[:500] + "…"
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": desc or f"Run skill {skill.name}",
                    "parameters": parameters,
                },
            }
        )
    return tools


def knowledge_base_ids_for_chat(
    customer_config: CustomerConfig | None,
) -> list[str] | None:
    if customer_config is None:
        return None
    return _ids_from_config(getattr(customer_config, "knowledge_base_ids", None))
