"""Built-in workflow graph templates (Beta)."""

from __future__ import annotations

from typing import Any

from app.data.patent_workflow_showcase import (
    apply_showcase_to_template,
    filter_showcase_templates,
)
from app.data.publish_workflow_templates import PUBLISH_WORKFLOW_TEMPLATES
from app.data.stock_workflow_templates import STOCK_TEMPLATES

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
                            "key": "report_title",
                            "label": "报告名称",
                            "placeholder": "根据检索词自动生成，可修改",
                            "required": False,
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
                        "year_from": "2020",
                        "year_to": "2024",
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
                        "title": "${input.report_title}",
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
                        "title": "${input.report_title}",
                        "filename": "${input.report_title}",
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
                            "key": "report_title",
                            "label": "Report title",
                            "placeholder": "Auto from keyword; editable",
                            "required": False,
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
                        "year_from": "2020",
                        "year_to": "2024",
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
                        "title": "${input.report_title}",
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
                        "title": "${input.report_title}",
                        "filename": "${input.report_title}",
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

WEB_FETCH_ZH: dict[str, Any] = {
    "id": "web_fetch",
    "locale": "zh",
    "name": "网页内容抓取",
    "description": "输入网站 URL，抓取并展示网页标题、正文等内容，支持代理和正则提取。",
    "category": "general",
    "graph_json": {
        "version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "输入网站 URL",
                "position": {"x": 40, "y": 120},
                "config": {
                    "input_fields": [
                        {
                            "key": "url",
                            "label": "网站 URL",
                            "placeholder": "https://example.com",
                            "required": True,
                        },
                        {
                            "key": "proxy",
                            "label": "使用代理",
                            "placeholder": "true / false",
                            "required": False,
                        },
                        {
                            "key": "format",
                            "label": "输出格式",
                            "placeholder": "markdown / text / json / html",
                            "required": False,
                        },
                    ],
                },
            },
            {
                "id": "fetch",
                "type": "skill",
                "name": "抓取网页",
                "position": {"x": 320, "y": 120},
                "config": {
                    "skill_name": "web-fetch",
                    "workflow_role": "search",
                    "payload_template": {
                        "command": "fetch",
                        "url": "${input.url}",
                        "proxy": "${input.proxy}",
                        "format": "${input.format}",
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
            {"id": "e_start_fetch", "source": "start", "target": "fetch"},
            {"id": "e_fetch_end", "source": "fetch", "target": "end"},
        ],
    },
}

WEB_FETCH_EN: dict[str, Any] = {
    "id": "web_fetch_en",
    "locale": "en",
    "name": "Web Page Fetcher",
    "description": "Enter a URL to fetch and display page content, with proxy and regex support.",
    "category": "general",
    "graph_json": {
        "version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Enter URL",
                "position": {"x": 40, "y": 120},
                "config": {
                    "input_fields": [
                        {
                            "key": "url",
                            "label": "Website URL",
                            "placeholder": "https://example.com",
                            "required": True,
                        },
                        {
                            "key": "use_proxy",
                            "label": "Use proxy",
                            "placeholder": "true / false",
                            "required": False,
                        },
                        {
                            "key": "format",
                            "label": "Output format",
                            "placeholder": "markdown / text / json / html",
                            "required": False,
                        },
                    ],
                },
            },
            {
                "id": "fetch",
                "type": "skill",
                "name": "Fetch page",
                "position": {"x": 320, "y": 120},
                "config": {
                    "skill_name": "web-fetch",
                    "workflow_role": "search",
                    "payload_template": {
                        "command": "fetch",
                        "url": "${input.url}",
                        "proxy": "${input.proxy}",
                        "format": "${input.format}",
                    },
                },
            },
            {
                "id": "end",
                "type": "end",
                "name": "Done",
                "position": {"x": 560, "y": 120},
                "config": {},
            },
        ],
        "edges": [
            {"id": "e_start_fetch", "source": "start", "target": "fetch"},
            {"id": "e_fetch_end", "source": "fetch", "target": "end"},
        ],
    },
}

BATCH_URL_FETCH: dict[str, Any] = {
    "id": "batch_url_fetch",
    "locale": "zh",
    "name": "批量网页抓取",
    "description": "输入多个 URL（每行一个），批量抓取每个网页的标题和正文。",
    "category": "general",
    "graph_json": {
        "version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "输入 URL 列表",
                "position": {"x": 40, "y": 120},
                "config": {
                    "input_fields": [
                        {
                            "key": "urls",
                            "label": "网站 URL（每行一个）",
                            "placeholder": "https://example.com\nhttps://httpbin.org/get",
                            "required": True,
                            "type": "multiline",
                        },
                        {
                            "key": "proxy",
                            "label": "使用代理",
                            "placeholder": "true / false（留空=否）",
                            "required": False,
                        },
                    ],
                },
            },
            {
                "id": "batch",
                "type": "batch",
                "name": "逐个抓取",
                "position": {"x": 360, "y": 120},
                "config": {
                    "list_path": "input.urls",
                    "max_concurrent": 3,
                },
            },
            {
                "id": "fetch_child",
                "type": "skill",
                "name": "web-fetch",
                "parentId": "batch",
                "position": {"x": 20, "y": 70},
                "config": {
                    "skill_name": "web-fetch",
                    "payload_template": {
                        "command": "fetch",
                        "url": "${item.line}",
                        "format": "text",
                        "max_length": 5000,
                    },
                },
            },
            {
                "id": "end",
                "type": "end",
                "name": "完成",
                "position": {"x": 640, "y": 120},
                "config": {},
            },
        ],
        "edges": [
            {"id": "e_start_batch", "source": "start", "target": "batch"},
            {"id": "e_batch_end", "source": "batch", "target": "end"},
        ],
    },
}

BATCH_URL_FETCH_EN: dict[str, Any] = {
    "id": "batch_url_fetch_en",
    "locale": "en",
    "name": "Batch URL Fetcher",
    "description": "Enter multiple URLs (one per line) to batch-fetch each page's title and content.",
    "category": "general",
    "graph_json": {
        "version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Enter URL list",
                "position": {"x": 40, "y": 120},
                "config": {
                    "input_fields": [
                        {
                            "key": "urls",
                            "label": "Website URLs (one per line)",
                            "placeholder": "https://example.com\nhttps://httpbin.org/get",
                            "required": True,
                        },
                        {
                            "key": "proxy",
                            "label": "Use proxy",
                            "placeholder": "true / false (blank=no)",
                            "required": False,
                        },
                    ],
                },
            },
            {
                "id": "batch",
                "type": "batch",
                "name": "Fetch each",
                "position": {"x": 360, "y": 120},
                "config": {
                    "list_path": "input.urls",
                    "item_key": "line",
                    "skill_name": "web-fetch",
                    "max_concurrent": 3,
                    "payload_template": {
                        "command": "fetch",
                        "url": "${item.line}",
                        "format": "text",
                        "max_length": 5000,
                    },
                },
            },
            {
                "id": "end",
                "type": "end",
                "name": "Done",
                "position": {"x": 640, "y": 120},
                "config": {},
            },
        ],
        "edges": [
            {"id": "e_start_batch", "source": "start", "target": "batch"},
            {"id": "e_batch_end", "source": "batch", "target": "end"},
        ],
    },
}

# -- Content auto-publish (read uploads → write copy → publish to channel) ----
# Demonstrates the full content-distribution pipeline. Pairs with the
# read-uploads / content-writer / publish-content skills. Bind a Schedule to
# run it daily; the {yyyy.MM.dd} path token auto-resolves to "today".

TEA_DAILY_PUBLISH: dict[str, Any] = {
    "id": "tea_daily_publish",
    "locale": "zh",
    "name": "茶叶日报多渠道推送",
    "description": "读取当日上传区 tea/{yyyy.MM.dd} 资料 → AI 生成文案 → 并行发布到飞书群 + 小红书。配合定时器每日自动运行。两条渠道独立，互不影响。",
    "category": "publish",
    "graph_json": {
        "version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "推送参数",
                "position": {"x": 40, "y": 220},
                "config": {
                    "input_fields": [
                        {
                            "key": "topic",
                            "label": "今日主题",
                            "placeholder": "白茶·白毫银针 上市",
                            "required": True,
                        },
                        {
                            "key": "style",
                            "label": "文案风格",
                            "placeholder": "xiaohongshu / wechat_mp / feishu",
                            "required": False,
                        },
                        {
                            "key": "webhook_url",
                            "label": "飞书机器人 Webhook",
                            "placeholder": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
                            "required": True,
                        },
                        {
                            "key": "xhs_image_path",
                            "label": "小红书配图绝对路径(可选)",
                            "placeholder": "/abs/path/to/tea.jpg；留空则仅飞书",
                            "required": False,
                        },
                    ],
                },
            },
            {
                "id": "read",
                "type": "skill",
                "name": "读取当日资料",
                "position": {"x": 320, "y": 220},
                "config": {
                    "skill_name": "read-uploads",
                    "workflow_role": "source",
                    "timeout_seconds": 30,
                    "payload_template": {
                        "subdir": "user",
                        "path": "tea/{yyyy.MM.dd}",
                        "pattern": "*.md",
                        "format": "content",
                    },
                },
            },
            {
                "id": "writer",
                "type": "skill",
                "name": "AI 生成文案",
                "position": {"x": 600, "y": 220},
                "config": {
                    "skill_name": "content-writer",
                    "workflow_role": "action",
                    "timeout_seconds": 180,
                    "payload_template": {
                        "topic": "${input.topic}",
                        "material": "${nodes.read.content}",
                        "style": "${input.style}",
                    },
                },
            },
            {
                "id": "publish_feishu",
                "type": "skill",
                "name": "发布到飞书",
                "position": {"x": 900, "y": 80},
                "config": {
                    "skill_name": "publish-content",
                    "workflow_role": "action",
                    "timeout_seconds": 60,
                    "payload_template": {
                        "provider": "feishu",
                        "channel_config": {
                            "webhook_url": "${input.webhook_url}",
                            "msg_type": "text",
                        },
                        "title": "${nodes.writer.title}",
                        "content": "${nodes.writer.content}",
                    },
                },
            },
            {
                "id": "publish_xhs",
                "type": "skill",
                "name": "发布到小红书",
                "position": {"x": 900, "y": 360},
                "config": {
                    "skill_name": "publish-content",
                    "workflow_role": "action",
                    "timeout_seconds": 300,
                    "payload_template": {
                        "provider": "playwright_client",
                        "channel_config": {
                            "platform": "xiaohongshu",
                            "timeout_seconds": 240,
                        },
                        "title": "${nodes.writer.title}",
                        "content": "${nodes.writer.content}",
                        "media": [
                            {"type": "image", "path": "${input.xhs_image_path}"},
                        ],
                    },
                },
            },
            {
                "id": "merge",
                "type": "merge",
                "name": "汇总结果",
                "position": {"x": 1200, "y": 220},
                "config": {},
            },
            {
                "id": "end",
                "type": "end",
                "name": "完成",
                "position": {"x": 1440, "y": 220},
                "config": {},
            },
        ],
        "edges": [
            {"id": "e_start_read", "source": "start", "target": "read"},
            {"id": "e_read_writer", "source": "read", "target": "writer"},
            {"id": "e_writer_feishu", "source": "writer", "target": "publish_feishu"},
            {"id": "e_writer_xhs", "source": "writer", "target": "publish_xhs"},
            {"id": "e_feishu_merge", "source": "publish_feishu", "target": "merge"},
            {"id": "e_xhs_merge", "source": "publish_xhs", "target": "merge"},
            {"id": "e_merge_end", "source": "merge", "target": "end"},
        ],
    },
}

TEA_DAILY_PUBLISH_EN: dict[str, Any] = {
    "id": "tea_daily_publish_en",
    "locale": "en",
    "name": "Tea Daily Multi-Channel Publish",
    "description": "Read today's tea/{yyyy.MM.dd} uploads → AI writes a post → publish in parallel to a Feishu group + Xiaohongshu. Two independent channels. Pair with a Schedule for daily runs.",
    "category": "publish",
    "graph_json": {
        "version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "name": "Publish Parameters",
                "position": {"x": 40, "y": 220},
                "config": {
                    "input_fields": [
                        {
                            "key": "topic",
                            "label": "Today's topic",
                            "placeholder": "New harvest: Silver Needle white tea",
                            "required": True,
                        },
                        {
                            "key": "style",
                            "label": "Copy style",
                            "placeholder": "xiaohongshu / wechat_mp / feishu",
                            "required": False,
                        },
                        {
                            "key": "webhook_url",
                            "label": "Feishu bot webhook",
                            "placeholder": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
                            "required": True,
                        },
                        {
                            "key": "xhs_image_path",
                            "label": "Xiaohongshu image path (optional)",
                            "placeholder": "/abs/path/to/tea.jpg; leave empty for Feishu only",
                            "required": False,
                        },
                    ],
                },
            },
            {
                "id": "read",
                "type": "skill",
                "name": "Read today's material",
                "position": {"x": 320, "y": 220},
                "config": {
                    "skill_name": "read-uploads",
                    "workflow_role": "source",
                    "timeout_seconds": 30,
                    "payload_template": {
                        "subdir": "user",
                        "path": "tea/{yyyy.MM.dd}",
                        "pattern": "*.md",
                        "format": "content",
                    },
                },
            },
            {
                "id": "writer",
                "type": "skill",
                "name": "AI copy writing",
                "position": {"x": 600, "y": 220},
                "config": {
                    "skill_name": "content-writer",
                    "workflow_role": "action",
                    "timeout_seconds": 180,
                    "payload_template": {
                        "topic": "${input.topic}",
                        "material": "${nodes.read.content}",
                        "style": "${input.style}",
                    },
                },
            },
            {
                "id": "publish_feishu",
                "type": "skill",
                "name": "Publish to Feishu",
                "position": {"x": 900, "y": 80},
                "config": {
                    "skill_name": "publish-content",
                    "workflow_role": "action",
                    "timeout_seconds": 60,
                    "payload_template": {
                        "provider": "feishu",
                        "channel_config": {
                            "webhook_url": "${input.webhook_url}",
                            "msg_type": "text",
                        },
                        "title": "${nodes.writer.title}",
                        "content": "${nodes.writer.content}",
                    },
                },
            },
            {
                "id": "publish_xhs",
                "type": "skill",
                "name": "Publish to Xiaohongshu",
                "position": {"x": 900, "y": 360},
                "config": {
                    "skill_name": "publish-content",
                    "workflow_role": "action",
                    "timeout_seconds": 300,
                    "payload_template": {
                        "provider": "playwright_client",
                        "channel_config": {
                            "platform": "xiaohongshu",
                            "timeout_seconds": 240,
                        },
                        "title": "${nodes.writer.title}",
                        "content": "${nodes.writer.content}",
                        "media": [
                            {"type": "image", "path": "${input.xhs_image_path}"},
                        ],
                    },
                },
            },
            {
                "id": "merge",
                "type": "merge",
                "name": "Merge results",
                "position": {"x": 1200, "y": 220},
                "config": {},
            },
            {
                "id": "end",
                "type": "end",
                "name": "Done",
                "position": {"x": 1440, "y": 220},
                "config": {},
            },
        ],
        "edges": [
            {"id": "e_start_read", "source": "start", "target": "read"},
            {"id": "e_read_writer", "source": "read", "target": "writer"},
            {"id": "e_writer_feishu", "source": "writer", "target": "publish_feishu"},
            {"id": "e_writer_xhs", "source": "writer", "target": "publish_xhs"},
            {"id": "e_feishu_merge", "source": "publish_feishu", "target": "merge"},
            {"id": "e_xhs_merge", "source": "publish_xhs", "target": "merge"},
            {"id": "e_merge_end", "source": "merge", "target": "end"},
        ],
    },
}

_BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    PATENT_REPORT_MULTIDIM["id"]: PATENT_REPORT_MULTIDIM,
    PATENT_REPORT_MULTIDIM_EN["id"]: PATENT_REPORT_MULTIDIM_EN,
    NOTIFY_PING_TEST["id"]: NOTIFY_PING_TEST,
    NOTIFY_PING_TEST_EN["id"]: NOTIFY_PING_TEST_EN,
    WEB_FETCH_ZH["id"]: WEB_FETCH_ZH,
    WEB_FETCH_EN["id"]: WEB_FETCH_EN,
    BATCH_URL_FETCH["id"]: BATCH_URL_FETCH,
    BATCH_URL_FETCH_EN["id"]: BATCH_URL_FETCH_EN,
    TEA_DAILY_PUBLISH["id"]: TEA_DAILY_PUBLISH,
    TEA_DAILY_PUBLISH_EN["id"]: TEA_DAILY_PUBLISH_EN,
    **PUBLISH_WORKFLOW_TEMPLATES,
    **STOCK_TEMPLATES,
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
