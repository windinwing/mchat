"""Post-process assistant text: turn plain CN patent IDs into Markdown links."""

from __future__ import annotations

import re
from typing import Any

from app.core.config import settings

# 中国发明专利公开号常见形态
_PATENT_ID_RE = re.compile(r"\b(CN\d{6,}[A-Z0-9]{0,3})\b")

# 已是 Markdown 链接的片段，避免重复包裹
_MD_LINK_CHUNK_RE = re.compile(r"(\[[^\]]+\]\([^)]+\))")


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def default_patent_portal_url_template() -> str:
    """Default patent portal URL template; configurable via env PATENT_PORTAL_URL_TEMPLATE."""
    explicit = (getattr(settings, "patent_portal_url_template", None) or "").strip()
    if explicit:
        return explicit
    base = (getattr(settings, "patent9235_base_url", None) or "").strip().rstrip("/")
    if base:
        return f"{base}/patent/{{patent_id}}.html"
    return "https://www.9235.net/patent/{patent_id}.html"


def patent_link_settings_from_skills(tool_skills: list[Any]) -> dict[str, Any]:
    """Read link settings from patent-search skill secrets / config."""
    for skill in tool_skills:
        if (getattr(skill, "name", None) or "") != "patent-search":
            continue
        config = getattr(skill, "config", None) or {}
        secrets = config.get("secrets") or config.get("env") or {}
        if not isinstance(secrets, dict):
            secrets = {}
        has_explicit = (
            secrets.get("show_external_patent_url")
            or config.get("show_external_patent_url")
        )
        template = (
            secrets.get("patent_portal_url_template")
            or secrets.get("patentUrl")
            or secrets.get("patent_url")
            or config.get("patent_portal_url_template")
            or config.get("patentUrl")
            or config.get("patent_url")
            or default_patent_portal_url_template()
        )
        template_raw = str(template)
        if "{patent_id}" not in template_raw:
            template_raw = template_raw.rstrip("/") + "/{patent_id}.html"
        enabled = _coerce_bool(has_explicit) if has_explicit is not None else bool(template_raw)
        return {"enabled": enabled, "template": template_raw}
    fallback = default_patent_portal_url_template()
    return {"enabled": bool(fallback), "template": fallback}


def _portal_url(patent_id: str, template: str) -> str:
    return template.replace("{patent_id}", patent_id).replace("{patentId}", patent_id)


def linkify_patent_ids(text: str, *, enabled: bool, template: str) -> str:
    if not enabled or not text:
        return text

    def _link_plain(segment: str) -> str:
        def repl(match: re.Match[str]) -> str:
            pid = match.group(1)
            return f"[{pid}]({_portal_url(pid, template)})"

        return _PATENT_ID_RE.sub(repl, segment)

    parts = _MD_LINK_CHUNK_RE.split(text)
    return "".join(
        part if _MD_LINK_CHUNK_RE.fullmatch(part) else _link_plain(part)
        for part in parts
    )


def inject_action_links(text: str) -> str:
    """Auto-wrap common operation text as [label](action:command) links.
    Works around LLMs stripping unknown protocols from markdown links."""
    # Single-line operation pills: "下一页 · 排序 · 导出Excel"
    def _wrap_ops(match: re.Match) -> str:
        items = [i.strip() for i in re.split(r'\s*[·|]\s*', match.group(1)) if i.strip()]
        if len(items) <= 1:
            return match.group(0)
        linked = [f'[{item}](action:{item})' for item in items]
        return ' · '.join(linked)

    text = re.sub(
        r'(?:^|\n)([^·\n]+(?:·[^·\n]+){2,})',
        _wrap_ops,
        text,
        flags=re.MULTILINE,
    )
    # Bullet points after operation headers
    def _link_ops(match: re.Match) -> str:
        label = match.group(1)
        cmd = match.group(2)
        return f'- [{label}](action:{cmd})'

    text = re.sub(
        r'[-\*]\s*([^：\n]+)[：:]\s*[「「]?([^」」\n]+)[」」]?',
        _link_ops,
        text,
    )
    return text
