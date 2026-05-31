"""Tests for multi-root skills paths and patent workflow showcase config."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import skills_paths
from app.core.config import settings
from app.data.patent_workflow_showcase import (
    apply_showcase_skill_names,
    filter_showcase_templates,
    resolve_showcase_skill_name,
)
from app.data.workflow_templates import get_workflow_template
from app.skill.loader import SkillLoader


def test_parse_extra_skills_dirs(monkeypatch):
    monkeypatch.chdir("/")
    roots = skills_paths.parse_extra_skills_dirs("/tmp/a,/tmp/b:/tmp/c")
    assert len(roots) == 3
    assert roots[0].resolve() == Path("/tmp/a").resolve()


def test_loader_scans_extra_dir(tmp_path, monkeypatch):
    primary = tmp_path / "primary"
    extra = tmp_path / "extra"
    primary.mkdir()
    extra.mkdir()
    (primary / "mchat-help").mkdir()
    (primary / "mchat-help" / "SKILL.md").write_text(
        "---\nname: mchat-help\ndescription: help\ntype: tool\n---\n",
        encoding="utf-8",
    )
    (extra / "patent-search").mkdir()
    (extra / "patent-search" / "SKILL.md").write_text(
        "---\nname: patent-search\ndescription: search\ntype: tool\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "skills_dir", str(primary))
    monkeypatch.setattr(settings, "extra_skills_dirs", str(extra))

    names = {s["name"] for s in SkillLoader().scan_skills()}
    assert "mchat-help" in names or "patent-search" in names
    assert "patent-search" in names


def test_showcase_skill_name_mapping(monkeypatch):
    monkeypatch.setattr(settings, "patent_workflow_search_skill", "my-search")
    monkeypatch.setattr(settings, "patent_workflow_report_skill", "my-report")
    assert resolve_showcase_skill_name("patent-search") == "my-search"
    assert resolve_showcase_skill_name("patent-report") == "my-report"


def test_apply_showcase_to_builtin_template(monkeypatch):
    monkeypatch.setattr(settings, "patent_workflow_report_skill", "custom-report")
    tpl = get_workflow_template("patent_report_multidim")
    assert tpl is not None
    chart = next(n for n in tpl["graph_json"]["nodes"] if n["id"] == "chart")
    assert chart["config"]["skill_name"] == "custom-report"


def test_filter_showcase_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "patent_workflow_showcase_enabled", False)
    rows = [
        {"id": "patent_report_multidim", "category": "patent"},
        {"id": "other", "category": "general"},
    ]
    filtered = filter_showcase_templates(rows)
    assert len(filtered) == 1
    assert filtered[0]["id"] == "other"


def test_apply_showcase_skill_names_rewrites_graph():
    graph = {
        "nodes": [
            {"id": "a", "config": {"skill_name": "patent-search"}},
            {"id": "b", "config": {"skill_name": "other-skill"}},
        ]
    }
    out = apply_showcase_skill_names(graph)
    assert out["nodes"][0]["config"]["skill_name"] == "patent-search"
    assert out["nodes"][1]["config"]["skill_name"] == "other-skill"
