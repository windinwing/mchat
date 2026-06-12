"""Patent-search skill follow-up prompts (kept out of core engine)."""

from __future__ import annotations

from typing import Any

from app.models.skill import Skill

_DEFAULT_PRESENTATION_NUDGE = (
    "（用户看不到本条消息。）\n"
    "请按以下结构生成回复，只生成一遍：\n\n"
    "🔍 搜索完成\n"
    "📊 找到 N 条专利\n"
    "\n"
    "制表符分隔表格（序号\t专利号\t标题\t申请人\t申请日\t公开日），逐行展示结果。\n"
    "\n"
    "📄 当前仅展示前 N 条，共 N 条匹配。\n"
    "\n"
    "初步观察：4-6条要点列表概括。\n"
    "\n"
    "最后一行，用 · 分隔列出后续操作（只写操作名，不要写解释文本）：\n"
    "下一页 · 按最新公开排序 · 按最新申请排序 · 导出Excel · 分析申请人分布 · 分析IPC分布\n"
    "\n"
    "绝对禁止：表格只能出现一次。"
    "不要输出 command= / page=。"
    "操作建议用 · 分隔，一行内写完，不要再另起一行解释。"
)

_DEFAULT_OBSERVATION_NUDGE = (
    "（专利检索结果表格已在上方展示给用户，用户看不到本条消息。）\n"
    "请用中文写一段回复，以小标题「初步观察」开头，接着用 4–6 条要点（列表即可）概括："
    "主要申请人类型（企业/高校/外资等）、代表性机构、技术方向、以及总申请量说明；\n"
    "绝对不要重复表格、不要罗列专利号、不要写 command= / page= 等技术参数。\n"
    "后续操作建议用 [操作名](action:用户要说的话) 格式。"
)

_DEFAULT_TOOL_HINT = (
    "\n\n## Tool: patent-search\n"
    "- search（默认）: query + 可选 page, page_size, details, scope, sort\n"
    "- 用户要「最新/最近」专利：必须传 sort=!documentDate；"
    "「最新申请/按申请日」传 sort=!applicationDate；"
    "「最新公开/按公开日」传 sort=!documentDate。\n"
    "- ⚠️ 用户点击操作 pill（如「按最新公开排序」）后，你必须**复用上一次搜索的 query**，"
    "只改 sort 参数，不要把操作文本当成检索词。"
    "例如上一条 query=「无人机」，用户点「按最新公开排序」，"
    "你应该传 query=「无人机」 sort=!documentDate。\n"
    "- page: 翻页时改 page 参数，保持 query 和 sort 不变。\n"
    "- export: 传 command=export、query（如「华为」）。用户说「导出/下载 Excel/表格」时必须用此命令。"
    "导出后会返回下载链接。\n"
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


_DEFAULT_EXPORT_NUDGE = (
    "（用户看不到本条消息。下载链接已在上方显示。）\n"
    "请用一句话确认导出成功（如「已导出 N 条记录」），然后给 2-3 条后续操作建议"
    "（如翻页导出、统计分析、专利详情）。\n"
    "⚠️ 禁止生成下载链接！链接已在上方展示，不要重复。"
    "不要写 command= / page= 等技术参数。"
)


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
    if tool_name != "patent-search" or command not in ("search", "export"):
        return False
    if not tool_display or tool_display.lstrip().startswith("❌"):
        return False
    return any(marker in tool_display for marker in _SUCCESS_MARKERS)
