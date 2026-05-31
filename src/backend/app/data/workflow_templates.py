"""Built-in workflow graph templates (Beta)."""

from __future__ import annotations

from typing import Any

from app.data.patent_workflow_showcase import (
    apply_showcase_to_template,
    filter_showcase_templates,
)

PATENT_REPORT_MULTIDIM: dict[str, Any] = {
    "id": "patent_report_multidim",
    "locale": "zh",
    "name": "专利多维分析报表",
    "description": "检索行业专利后，并行执行申请人/年份/企业/强度分析，汇总生成图表并导出报告。",
    "category": "patent",
    "graph_json": {
        "version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "输入参数",
                "position": {"x": 40, "y": 220},
                "config": {
                    "input_fields": [
                        {
                            "key": "keyword",
                            "label": "检索关键词",
                            "placeholder": "无人机",
                            "required": True,
                        },
                        {
                            "key": "industry",
                            "label": "行业",
                            "placeholder": "航空航天",
                            "required": False,
                        },
                    ]
                },
            },
            {
                "id": "search",
                "type": "skill",
                "name": "行业专利检索",
                "position": {"x": 280, "y": 220},
                "config": {
                    "skill_name": "patent-search",
                    "workflow_role": "search",
                    "payload_template": {
                        "command": "search",
                        "query": "${input.keyword}",
                        "industry": "${input.industry}",
                    },
                },
            },
            {
                "id": "applicant",
                "type": "skill",
                "name": "申请人分析",
                "position": {"x": 560, "y": 40},
                "config": {
                    "skill_name": "patent-search",
                    "workflow_role": "analyze",
                    "payload_template": {
                        "command": "analysis",
                        "query": "${input.keyword}",
                        "dimension": "applicant",
                    },
                },
            },
            {
                "id": "year",
                "type": "skill",
                "name": "年份趋势",
                "position": {"x": 560, "y": 140},
                "config": {
                    "skill_name": "patent-search",
                    "workflow_role": "analyze",
                    "payload_template": {
                        "command": "analysis",
                        "query": "${input.keyword}",
                        "dimension": "applicationYear",
                    },
                },
            },
            {
                "id": "company",
                "type": "skill",
                "name": "区域分布",
                "position": {"x": 560, "y": 240},
                "config": {
                    "skill_name": "patent-search",
                    "workflow_role": "analyze",
                    "payload_template": {
                        "command": "analysis",
                        "query": "${input.keyword}",
                        "dimension": "province",
                    },
                },
            },
            {
                "id": "strength",
                "type": "skill",
                "name": "法律状态",
                "position": {"x": 560, "y": 340},
                "config": {
                    "skill_name": "patent-search",
                    "workflow_role": "analyze",
                    "payload_template": {
                        "command": "analysis",
                        "query": "${input.keyword}",
                        "dimension": "legalStatus",
                    },
                },
            },
            {
                "id": "merge",
                "type": "merge",
                "name": "汇总分析结果",
                "position": {"x": 840, "y": 220},
                "config": {"merge_mode": "sections"},
            },
            {
                "id": "chart",
                "type": "skill",
                "name": "图表生成",
                "position": {"x": 1080, "y": 220},
                "config": {
                    "skill_name": "patent-report",
                    "workflow_role": "visualize",
                    "payload_template": {
                        "command": "chart",
                        "sections": "${nodes.merge.sections}",
                        "title": "${input.keyword} 专利分析",
                    },
                },
            },
            {
                "id": "export",
                "type": "skill",
                "name": "报告导出",
                "position": {"x": 1320, "y": 220},
                "config": {
                    "skill_name": "patent-report",
                    "workflow_role": "export",
                    "payload_template": {
                        "command": "all",
                        "sections": "${nodes.merge.sections}",
                        "charts": "${nodes.chart.charts}",
                        "title": "${input.keyword} 专利分析",
                        "filename": "${input.keyword}-patent-report",
                    },
                },
            },
            {
                "id": "end",
                "type": "end",
                "name": "完成",
                "position": {"x": 1560, "y": 220},
                "config": {},
            },
        ],
        "edges": [
            {"id": "e_start_search", "source": "start", "target": "search"},
            {"id": "e_search_applicant", "source": "search", "target": "applicant"},
            {"id": "e_search_year", "source": "search", "target": "year"},
            {"id": "e_search_company", "source": "search", "target": "company"},
            {"id": "e_search_strength", "source": "search", "target": "strength"},
            {"id": "e_applicant_merge", "source": "applicant", "target": "merge"},
            {"id": "e_year_merge", "source": "year", "target": "merge"},
            {"id": "e_company_merge", "source": "company", "target": "merge"},
            {"id": "e_strength_merge", "source": "strength", "target": "merge"},
            {"id": "e_merge_chart", "source": "merge", "target": "chart"},
            {"id": "e_chart_export", "source": "chart", "target": "export"},
            {"id": "e_export_end", "source": "export", "target": "end"},
        ],
    },
}

# English template: same executable topology as zh (patent-search + analysis); chart node remains optional placeholder.
PATENT_REPORT_MULTIDIM_EN: dict[str, Any] = {
    "id": "patent_report_multidim_en",
    "locale": "en",
    "name": "Patent Multi-Dimension Report",
    "description": "Executable report flow: patent-search search + parallel analysis dimensions, merge, chart (patent-report), full Office export.",
    "category": "patent",
    "graph_json": {
        "version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Input Parameters",
                "position": {"x": 40, "y": 220},
                "config": {
                    "input_fields": [
                        {
                            "key": "keyword",
                            "label": "Search keyword",
                            "placeholder": "drone",
                            "required": True,
                        },
                        {
                            "key": "industry",
                            "label": "Industry",
                            "placeholder": "aerospace",
                            "required": False,
                        },
                    ]
                },
            },
            {
                "id": "search",
                "type": "skill",
                "name": "Industry Patent Search",
                "position": {"x": 280, "y": 220},
                "config": {
                    "skill_name": "patent-search",
                    "workflow_role": "search",
                    "payload_template": {
                        "command": "search",
                        "query": "${input.keyword}",
                        "industry": "${input.industry}",
                    },
                },
            },
            {
                "id": "applicant",
                "type": "skill",
                "name": "Applicant Analysis",
                "position": {"x": 560, "y": 40},
                "config": {
                    "skill_name": "patent-search",
                    "workflow_role": "analyze",
                    "payload_template": {
                        "command": "analysis",
                        "query": "${input.keyword}",
                        "dimension": "applicant",
                    },
                },
            },
            {
                "id": "year",
                "type": "skill",
                "name": "Application Year Trend",
                "position": {"x": 560, "y": 140},
                "config": {
                    "skill_name": "patent-search",
                    "workflow_role": "analyze",
                    "payload_template": {
                        "command": "analysis",
                        "query": "${input.keyword}",
                        "dimension": "applicationYear",
                    },
                },
            },
            {
                "id": "company",
                "type": "skill",
                "name": "Regional Distribution",
                "position": {"x": 560, "y": 240},
                "config": {
                    "skill_name": "patent-search",
                    "workflow_role": "analyze",
                    "payload_template": {
                        "command": "analysis",
                        "query": "${input.keyword}",
                        "dimension": "province",
                    },
                },
            },
            {
                "id": "strength",
                "type": "skill",
                "name": "Legal Status",
                "position": {"x": 560, "y": 340},
                "config": {
                    "skill_name": "patent-search",
                    "workflow_role": "analyze",
                    "payload_template": {
                        "command": "analysis",
                        "query": "${input.keyword}",
                        "dimension": "legalStatus",
                    },
                },
            },
            {
                "id": "merge",
                "type": "merge",
                "name": "Merge Analysis Results",
                "position": {"x": 840, "y": 220},
                "config": {"merge_mode": "sections"},
            },
            {
                "id": "chart",
                "type": "skill",
                "name": "Chart Generation",
                "position": {"x": 1080, "y": 220},
                "config": {
                    "skill_name": "patent-report",
                    "workflow_role": "visualize",
                    "payload_template": {
                        "command": "chart",
                        "sections": "${nodes.merge.sections}",
                        "title": "${input.keyword} patent analysis",
                    },
                },
            },
            {
                "id": "export",
                "type": "skill",
                "name": "Report Export",
                "position": {"x": 1320, "y": 220},
                "config": {
                    "skill_name": "patent-report",
                    "workflow_role": "export",
                    "payload_template": {
                        "command": "all",
                        "sections": "${nodes.merge.sections}",
                        "charts": "${nodes.chart.charts}",
                        "title": "${input.keyword} patent analysis",
                        "filename": "${input.keyword}-patent-report",
                    },
                },
            },
            {
                "id": "end",
                "type": "end",
                "name": "Done",
                "position": {"x": 1560, "y": 220},
                "config": {},
            },
        ],
        "edges": [
            {"id": "e_start_search", "source": "start", "target": "search"},
            {"id": "e_search_applicant", "source": "search", "target": "applicant"},
            {"id": "e_search_year", "source": "search", "target": "year"},
            {"id": "e_search_company", "source": "search", "target": "company"},
            {"id": "e_search_strength", "source": "search", "target": "strength"},
            {"id": "e_applicant_merge", "source": "applicant", "target": "merge"},
            {"id": "e_year_merge", "source": "year", "target": "merge"},
            {"id": "e_company_merge", "source": "company", "target": "merge"},
            {"id": "e_strength_merge", "source": "strength", "target": "merge"},
            {"id": "e_merge_chart", "source": "merge", "target": "chart"},
            {"id": "e_chart_export", "source": "chart", "target": "export"},
            {"id": "e_export_end", "source": "export", "target": "end"},
        ],
    },
}

NOTIFY_PING_TEST: dict[str, Any] = {
    "id": "notify_ping_test",
    "locale": "zh",
    "name": "短信通知 Ping 测试",
    "description": "验证 mchat-notify：dev 模式写后端日志；真发短信需本地安装 provider 插件。",
    "category": "notification",
    "graph_json": {
        "version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "输入手机号",
                "position": {"x": 40, "y": 120},
                "config": {
                    "input_fields": [
                        {
                            "key": "alert_phone",
                            "label": "告警手机号（须在白名单）",
                            "placeholder": "13800138000",
                            "required": True,
                        },
                    ]
                },
            },
            {
                "id": "notify",
                "type": "skill",
                "name": "短信 Ping",
                "position": {"x": 320, "y": 120},
                "config": {
                    "skill_name": "mchat-notify",
                    "payload_template": {
                        "command": "ping",
                        "phone": "${input.alert_phone}",
                        "provider": "dev",
                    },
                },
            },
            {
                "id": "end",
                "type": "end",
                "name": "完成",
                "position": {"x": 560, "y": 120},
                "config": {},
            },
        ],
        "edges": [
            {"id": "e_start_notify", "source": "start", "target": "notify"},
            {"id": "e_notify_end", "source": "notify", "target": "end"},
        ],
    },
}

NOTIFY_PING_TEST_EN: dict[str, Any] = {
    **NOTIFY_PING_TEST,
    "locale": "en",
    "name": "SMS notify ping test",
    "description": "Verify mchat-notify: dev mode logs only; install a local provider plugin for real SMS.",
    "graph_json": {
        **NOTIFY_PING_TEST["graph_json"],
        "nodes": [
            {
                **NOTIFY_PING_TEST["graph_json"]["nodes"][0],
                "name": "Phone input",
                "config": {
                    "input_fields": [
                        {
                            "key": "alert_phone",
                            "label": "Alert phone (must be allowlisted)",
                            "placeholder": "13800138000",
                            "required": True,
                        },
                    ]
                },
            },
            {
                **NOTIFY_PING_TEST["graph_json"]["nodes"][1],
                "name": "SMS ping",
            },
            {
                **NOTIFY_PING_TEST["graph_json"]["nodes"][2],
                "name": "Done",
            },
        ],
    },
}

_BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    PATENT_REPORT_MULTIDIM["id"]: PATENT_REPORT_MULTIDIM,
    PATENT_REPORT_MULTIDIM_EN["id"]: PATENT_REPORT_MULTIDIM_EN,
    NOTIFY_PING_TEST["id"]: NOTIFY_PING_TEST,
    NOTIFY_PING_TEST_EN["id"]: NOTIFY_PING_TEST_EN,
}


def list_workflow_templates(*, locale: str | None = None) -> list[dict[str, Any]]:
    rows = [
        {
            "id": tpl["id"],
            "name": tpl["name"],
            "description": tpl["description"],
            "category": tpl.get("category", "general"),
            "locale": tpl.get("locale"),
            "node_count": len(tpl["graph_json"].get("nodes") or []),
        }
        for tpl in _BUILTIN_TEMPLATES.values()
    ]
    rows = filter_showcase_templates(rows)
    if not locale:
        return rows
    lang = "zh" if locale.lower().startswith("zh") else "en"
    return [r for r in rows if not r.get("locale") or r.get("locale") == lang]


def get_workflow_template(template_id: str) -> dict[str, Any] | None:
    tpl = _BUILTIN_TEMPLATES.get(template_id)
    if not tpl:
        return None
    return apply_showcase_to_template(tpl)
