"""Patent workflow showcase — skill names & templates are configurable, not bundled in mchat."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.config import settings
from app.core.skills_paths import (
    PATENT_SHOWCASE_REPORT_SKILL,
    PATENT_SHOWCASE_SEARCH_SKILL,
)


def showcase_enabled() -> bool:
    return bool(getattr(settings, "patent_workflow_showcase_enabled", True))


def showcase_skill_map() -> dict[str, str]:
    """Map canonical template skill ids → configured installed skill names."""
    search = (
        getattr(settings, "patent_workflow_search_skill", None)
        or PATENT_SHOWCASE_SEARCH_SKILL
    ).strip()
    report = (
        getattr(settings, "patent_workflow_report_skill", None)
        or PATENT_SHOWCASE_REPORT_SKILL
    ).strip()
    return {
        PATENT_SHOWCASE_SEARCH_SKILL: search or PATENT_SHOWCASE_SEARCH_SKILL,
        PATENT_SHOWCASE_REPORT_SKILL: report or PATENT_SHOWCASE_REPORT_SKILL,
    }


def resolve_showcase_skill_name(canonical: str) -> str:
    return showcase_skill_map().get(canonical, canonical)


def apply_showcase_skill_names(graph_json: dict[str, Any] | None) -> dict[str, Any]:
    """Rewrite skill_name in graph nodes using configured showcase mapping."""
    if not graph_json:
        return {}
    graph = deepcopy(graph_json)
    mapping = showcase_skill_map()
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        cfg = node.get("config")
        if not isinstance(cfg, dict):
            continue
        skill_name = str(cfg.get("skill_name") or "").strip()
        if skill_name in mapping:
            cfg["skill_name"] = mapping[skill_name]
    return graph


def apply_showcase_to_template(template: dict[str, Any]) -> dict[str, Any]:
    tpl = deepcopy(template)
    tpl["graph_json"] = apply_showcase_skill_names(tpl.get("graph_json"))
    tpl["showcase"] = {
        "category": "patent",
        "search_skill": resolve_showcase_skill_name(PATENT_SHOWCASE_SEARCH_SKILL),
        "report_skill": resolve_showcase_skill_name(PATENT_SHOWCASE_REPORT_SKILL),
    }
    return tpl


def is_patent_showcase_template(template: dict[str, Any]) -> bool:
    return str(template.get("category") or "").strip().lower() == "patent"


def filter_showcase_templates(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if showcase_enabled():
        return templates
    return [t for t in templates if not is_patent_showcase_template(t)]
