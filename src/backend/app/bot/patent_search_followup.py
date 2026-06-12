"""Patent-search skill follow-up prompts (kept out of core engine)."""

from __future__ import annotations

from typing import Any

from app.models.skill import Skill

_DEFAULT_PRESENTATION_NUDGE = (
    "（用户看不到本条消息，专利检索结果表格已在工具调用中展示。）\n"
    "请根据上一条 patent-search 工具返回的结果，用中文给用户写分析，"
    "严格按以下结构（不要省略任何部分）：\n\n"
    "1. 小标题「初步观察」，接着 4–6 条要点（列表），概括申请人类型、"
    "代表性机构、技术方向、总量\n"
    "2. 结尾列出可继续操作：翻页、按公开日/申请日/相关度切换排序、统计分析、"
    "详情/权利要求/法律状态、企业专利画像等（排序话术见工具结果「排序方式」）\n"
    "⚠️ 禁止重复表格！工具调用已展示完整表格，你只写分析，不要复制专利列表。"
    "不要输出 tool_calls emoji 列表，不要写 command= / page= 等技术参数。"
)

_DEFAULT_OBSERVATION_NUDGE = (
    "（专利检索结果表格已在上方展示给用户，用户看不到本条消息。）\n"
    "请用中文写一段回复，以小标题「初步观察」开头，接着用 4–6 条要点（列表即可）概括："
    "主要申请人类型（企业/高校/外资等）、代表性机构、技术方向、以及总申请量说明；"
    "不要重复表格、不要罗列专利号、不要写 command= / page= 等技术参数。\n"
    "最后用 1–2 句自然语言说明：如需某条详情、权利要求、法律状态，"
    "或按公司、IPC、时间范围精确筛选，让用户直接告诉你即可。"
)

_DEFAULT_TOOL_HINT = (
    "\n\n## Tool: patent-search\n"
    "- search（默认）: query + 可选 page, page_size, details, scope, sort\n"
    "- 用户要「最新/最近」专利：必须传 sort=!documentDate；"
    "「最新申请/按申请日」传 sort=!applicationDate；"
    "query 可只写关键词（如「无人机」），勿丢掉排序意图\n"
    "- analysis: 必须同时传 command=analysis、query、dimension（applicant|ipc|"
    "applicationYear|legalStatus|province）\n"
    "- detail/claims/legal 等: 传 patent_id\n"
    "- company: 传 company_name（企业工商全称）\n"
    "- scope: cn 默认；全球/各国用 all|us|jp|kr|tw|wo|ep\n"
    "统计分析/详情/企业画像等命令会一次性返回完整结果，不要再次调用 search 重复列表。\n"
    "仅 search 成功且表格已展示后：再写「初步观察」式自然语言总结（要点列表），"
    "勿重复表格、勿向用户展示 command=/page= 等技术参数。"
)

_SUCCESS_MARKERS = (
    "🔍 搜索完成",
    "Search complete",
    "search complete",
)


def find_patent_search_skill(tool_skills: list[Skill]) -> Skill | None:
    for skill in tool_skills:
        if (skill.name or "") == "patent-search":
            return skill
    return None


def _skill_cfg(skill: Skill | None, key: str, default: Any) -> Any:
    if skill is None:
        return default
    config = skill.config or {}
    if key in config:
        return config[key]
    secrets = config.get("secrets") or config.get("env") or {}
    if isinstance(secrets, dict) and key in secrets:
        return secrets[key]
    return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def patent_search_enable_presentation(skill: Skill | None) -> bool:
    return _coerce_bool(
        _skill_cfg(skill, "enable_presentation_followup", True),
        True,
    )


def patent_search_enable_summary(skill: Skill | None) -> bool:
    return _coerce_bool(
        _skill_cfg(skill, "enable_observation_followup", False),
        False,
    )


def patent_search_presentation_nudge(skill: Skill | None) -> str:
    custom = _skill_cfg(skill, "presentation_nudge", None)
    if isinstance(custom, str) and custom.strip():
        return custom.strip()
    return _DEFAULT_PRESENTATION_NUDGE


def patent_search_observation_nudge(skill: Skill | None) -> str:
    custom = _skill_cfg(skill, "observation_nudge", None)
    if isinstance(custom, str) and custom.strip():
        return custom.strip()
    return _DEFAULT_OBSERVATION_NUDGE


def patent_search_tool_hint(skill: Skill | None = None) -> str:
    custom = _skill_cfg(skill, "tool_hint", None)
    if isinstance(custom, str) and custom.strip():
        return "\n\n" + custom.strip()
    return _DEFAULT_TOOL_HINT


def append_patent_tool_hints(system_prompt: str, tool_skills: list[Skill]) -> str:
    skill = find_patent_search_skill(tool_skills)
    if skill is None:
        return system_prompt
    return system_prompt + patent_search_tool_hint(skill)


def is_patent_search_success(
    tool_name: str, command: str, tool_display: str
) -> bool:
    if tool_name != "patent-search" or command != "search":
        return False
    if not tool_display or tool_display.lstrip().startswith("❌"):
        return False
    return any(marker in tool_display for marker in _SUCCESS_MARKERS)
