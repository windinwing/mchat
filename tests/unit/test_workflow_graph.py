"""Unit tests for workflow graph execution helpers."""

import json

import pytest

from app.data.workflow_templates import get_workflow_template, list_workflow_templates
from app.services.workflow_service import (
    _apply_patent_report_input,
    _default_report_title,
    _json_safe,
    _render_template,
    _resolve_path,
    _run_display_name,
)


def test_list_patent_report_template():
    templates = list_workflow_templates()
    assert any(t["id"] == "patent_report_multidim" for t in templates)
    assert any(t["id"] == "patent_report_multidim_en" for t in templates)
    tpl = get_workflow_template("patent_report_multidim")
    assert tpl is not None
    nodes = tpl["graph_json"]["nodes"]
    assert any(n["type"] == "merge" for n in nodes)
    search = next(n for n in nodes if n["id"] == "search")
    assert search["type"] == "skill"
    assert search["config"]["skill_name"] == "patent-search"
    applicant = next(n for n in nodes if n["id"] == "applicant")
    assert applicant["config"]["skill_name"] == "patent-search"
    assert applicant["config"]["payload_template"]["command"] == "analysis"
    en_tpl = get_workflow_template("patent_report_multidim_en")
    assert en_tpl is not None
    en_search = next(n for n in en_tpl["graph_json"]["nodes"] if n["id"] == "search")
    assert en_search["config"]["skill_name"] == "patent-search"
    en_export = next(n for n in en_tpl["graph_json"]["nodes"] if n["id"] == "export")
    assert en_export["config"]["skill_name"] == "patent-report"
    assert en_export["config"]["payload_template"]["command"] == "all"
    en_chart = next(n for n in en_tpl["graph_json"]["nodes"] if n["id"] == "chart")
    assert en_chart["config"]["skill_name"] == "patent-report"


def test_list_templates_by_locale():
    zh = list_workflow_templates(locale="zh")
    en = list_workflow_templates(locale="en")
    assert any(t["id"] == "patent_report_multidim" for t in zh)
    assert all(t.get("locale") in (None, "zh") for t in zh)
    assert any(t["id"] == "patent_report_multidim_en" for t in en)
    assert all(t.get("locale") in (None, "en") for t in en)


def test_render_template_input_and_nodes_path():
    context = {
        "input": {"keyword": "无人机", "industry": "航空航天"},
        "nodes": {
            "search": {"patent_ids": ["CN1", "CN2"], "total": 2},
        },
    }
    rendered = _render_template(
        {
            "query": "${input.keyword}",
            "industry": "${input.industry}",
            "patent_ids": "${nodes.search.patent_ids}",
        },
        context,
    )
    assert rendered["query"] == "无人机"
    assert rendered["industry"] == "航空航天"
    assert rendered["patent_ids"] == ["CN1", "CN2"]


def test_resolve_path_nested():
    context = {"nodes": {"merge": {"sections": {"a": 1}}}}
    assert _resolve_path("nodes.merge.sections", context) == {"a": 1}


def test_json_safe_breaks_end_node_cycle():
    """end node used to set result.output = live nodes dict → DB JSON failure."""
    nodes: dict = {"search": {"total": 10}}
    nodes["merge"] = {
        "sections": {"分析": {"node_id": "search", "result": nodes["search"]}}
    }
    nodes["end"] = {"output": nodes}
    with pytest.raises(ValueError, match="Circular"):
        json.dumps(nodes)
    safe = _json_safe({"outputs": nodes})
    parsed = json.loads(json.dumps(safe))
    assert parsed["outputs"]["search"]["total"] == 10


def test_default_report_title():
    assert "无人机" in _default_report_title("无人机")
    assert "专利分析报告" in _default_report_title("无人机")
    assert "航空航天" in _default_report_title("无人机", "航空航天")
    assert "Patent Analysis Report" in _default_report_title("drone", locale="en")


def test_apply_patent_report_input_overrides_title():
    payload = {
        "command": "all",
        "sections": {"x": 1},
        "title": "${input.keyword} 专利分析",
        "filename": "old-name",
    }
    out = _apply_patent_report_input(
        payload,
        {"keyword": "无人机", "report_title": "2024 无人机竞争格局分析"},
    )
    assert out["title"] == "2024 无人机竞争格局分析"
    assert out["filename"] == "2024 无人机竞争格局分析"


def test_apply_patent_report_input_falls_back_to_keyword():
    payload = {"command": "chart", "sections": []}
    out = _apply_patent_report_input(payload, {"keyword": "无人机", "industry": "低空经济"})
    assert "无人机" in out["title"]
    assert "低空经济" in out["title"]


def test_patent_template_has_report_title_field():
    tpl = get_workflow_template("patent_report_multidim")
    start = next(n for n in tpl["graph_json"]["nodes"] if n["id"] == "start")
    keys = [f["key"] for f in start["config"]["input_fields"]]
    assert "report_title" in keys
    export = next(n for n in tpl["graph_json"]["nodes"] if n["id"] == "export")
    assert export["config"]["payload_template"]["title"] == "${input.report_title}"


def test_run_display_name_prefers_run_label():
    assert _run_display_name({"run_label": "我的 Q1 报告", "report_title": "无人机"}, "专利多维分析报表") == "我的 Q1 报告"


def test_run_display_name_prefers_report_title():
    assert _run_display_name({"report_title": "2024 无人机竞争分析"}, "专利多维分析报表") == "2024 无人机竞争分析"
    assert _run_display_name({"keyword": "无人机"}, "专利多维分析报表") == "无人机"
    assert _run_display_name({}, "专利多维分析报表") == "专利多维分析报表"


def test_patent_template_year_on_skill_node():
    tpl = get_workflow_template("patent_report_multidim")
    start = next(n for n in tpl["graph_json"]["nodes"] if n["id"] == "start")
    keys = [f["key"] for f in start["config"]["input_fields"]]
    assert "year_from" not in keys
    year = next(n for n in tpl["graph_json"]["nodes"] if n["id"] == "year")
    assert year["config"]["payload_template"]["year_from"] == "2020"
    assert year["config"]["payload_template"]["year_to"] == "2024"


def test_graph_for_template_export_strips_skill_id():
    from app.services.workflow_service import graph_for_template_export

    graph = {
        "version": 1,
        "nodes": [
            {
                "id": "n1",
                "type": "skill",
                "config": {"skill_id": "skill-uuid-1", "skill_name": "patent-search"},
            }
        ],
        "edges": [],
    }
    exported = graph_for_template_export(graph, {"skill-uuid-1": "patent-search"})
    cfg = exported["nodes"][0]["config"]
    assert "skill_id" not in cfg
    assert cfg["skill_name"] == "patent-search"
