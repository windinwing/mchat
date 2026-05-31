"""Unit tests for workflow graph execution helpers."""

from app.data.workflow_templates import get_workflow_template, list_workflow_templates
from app.services.workflow_service import _render_template, _resolve_path


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
    assert en_search["config"]["skill_name"] == "patent-industry-search"


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
