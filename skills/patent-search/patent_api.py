#!/usr/bin/env python3
"""
专利检索API客户端 - 修复版
封装9235.net专利检索API
"""

import html
import os
import json
import re
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from urllib.parse import quote

# 说明书常见章节（用于分段标题）
_DESC_SECTIONS = (
    "技术领域",
    "背景技术",
    "发明内容",
    "实用新型内容",
    "附图说明",
    "具体实施方式",
    "说明书附图",
)


def parse_analysis_items(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """解析 /ration/analysis 响应（resultMap 或 analysis_total）。"""
    if not result or not result.get("success"):
        return []

    items = result.get("resultMap")
    if isinstance(items, list) and items:
        out = []
        for row in items:
            if not isinstance(row, dict):
                continue
            out.append(
                {
                    "key": row.get("key", "未知"),
                    "count": row.get("value", row.get("count", 0)),
                }
            )
        return out

    raw = result.get("analysis_total")
    if isinstance(raw, list):
        return [
            {
                "key": row.get("key", "未知"),
                "count": row.get("count", row.get("value", 0)),
            }
            for row in raw
            if isinstance(row, dict)
        ]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parse_analysis_items({"success": True, "resultMap": parsed})
        except json.JSONDecodeError:
            pass
    return []


def format_analysis_result(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """供 skill / mchat 调用，避免 from patent_api import 与动态模块名冲突。"""
    return parse_analysis_items(result)


_API_ERROR_MESSAGES = {
    202: "非法 Token，请检查 PATENT_API_TOKEN 是否有效",
    205: "参数为空",
    206: "未找到对应专利或数据",
    207: "当日该接口访问次数已用尽",
    208: "无访问权限",
    215: "异常访问，请通过检索接口获取专利 id 后再查询",
}

DEFAULT_PATENT_API_BASE = "https://www.9235.net/api"


def resolve_patent_api_base_url(
    base_url: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> str:
    """解析专利 API 根地址；9235 域名缺 /api 时企业画像等接口会 404。"""
    cfg = cfg or {}
    candidates = [
        base_url if base_url and base_url != DEFAULT_PATENT_API_BASE else None,
        os.environ.get("PATENT_API_BASE_URL"),
        os.environ.get("MCHAT_SKILL_PATENT_SEARCH_API_BASE_URL"),
        os.environ.get("api_base_url"),
        cfg.get("api_base_url"),
        DEFAULT_PATENT_API_BASE,
    ]
    raw = next((c for c in candidates if c and str(c).strip()), DEFAULT_PATENT_API_BASE)
    s = str(raw).strip().rstrip("/")
    if "9235.net" in s and not s.endswith("/api"):
        s = f"{s}/api"
    return s


def load_patent_skill_config() -> Dict[str, Any]:
    """读取技能目录 config.json（若存在）。"""
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def normalize_patent_url_template(raw: Optional[str]) -> Optional[str]:
    """
    将 patentUrl 规范为可 format 的模板。
    示例：https://www.9235.net/patent → https://www.9235.net/patent/{patent_id}.html
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if "{patent_id}" in s or "{patentId}" in s or "{id}" in s:
        return s
    return s.rstrip("/") + "/{patent_id}.html"


def build_patent_portal_url(patent_id: str, template: Optional[str]) -> Optional[str]:
    if not template:
        return None
    pid = (patent_id or "").strip()
    if not pid:
        return None
    return (
        template.replace("{patent_id}", pid)
        .replace("{patentId}", pid)
        .replace("{id}", pid)
    )


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _normalize_data_scope(scope: str | None) -> str:
    """与 9235 API 一致；权限由服务端按 Token 等级校验（≥7 可用全球库）。"""
    raw = (scope or "cn").strip().lower()
    if raw in ("cn", "all", "us", "jp", "kr", "tw", "wo", "ep"):
        return raw
    return "cn"


def api_result_ok(result: Dict[str, Any]) -> bool:
    if not result:
        return False
    if result.get("success") is False:
        return False
    code = result.get("code")
    if code is not None:
        try:
            if int(code) != 200:
                return False
        except (TypeError, ValueError):
            pass
    return True


def api_error_message(result: Dict[str, Any]) -> str:
    if not result or result.get("success"):
        return ""
    msg = result.get("message") or result.get("msg")
    if msg:
        return str(msg)
    code = result.get("code") or result.get("errorCode")
    if code is not None:
        try:
            return _API_ERROR_MESSAGES.get(int(code), f"错误码 {code}")
        except (TypeError, ValueError):
            pass
    return "未知错误"


def patent_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    p = result.get("patent")
    return p if isinstance(p, dict) else {}


def _sorted_map_rows(data: Any, limit: int = 12) -> list[tuple[str, int]]:
    if not isinstance(data, dict):
        return []
    rows: list[tuple[str, int]] = []
    for k, v in data.items():
        try:
            rows.append((str(k), int(v)))
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda x: (-x[1], x[0]))
    return rows[:limit]


def _kv_list_rows(data: Any, limit: int = 12) -> list[tuple[str, int]]:
    if not isinstance(data, list):
        return []
    rows: list[tuple[str, int]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        key = item.get("key") or item.get("name")
        val = item.get("value") or item.get("count")
        if key is None:
            continue
        try:
            rows.append((str(key), int(val or 0)))
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda x: (-x[1], x[0]))
    return rows[:limit]


def _append_count_table(
    output: list[str],
    title: str,
    rows: list[tuple[str, int]],
    *,
    col_a: str = "项目",
    col_b: str = "数量",
) -> None:
    if not rows:
        return
    output.append("")
    output.append(f"**{title}**")
    output.append("")
    output.append(f"| {col_a} | {col_b} |")
    output.append("| --- | ---: |")
    for name, count in rows:
        output.append(f"| {_md_table_cell(name, 48)} | {count:,} |")


def format_company_portrait(company_name: str, portrait: Dict[str, Any]) -> str:
    """格式化 /api/a/portrait 返回的 enterprisePortrait。"""
    output = [
        f"### 企业画像：{company_name}",
        "",
        "> 企业名称请使用**工商全称**（如「华为技术有限公司」），简称可能查无数据。",
    ]
    legal = _sorted_map_rows(portrait.get("legalMap"))
    types = _sorted_map_rows(portrait.get("typeMap"))
    areas = _sorted_map_rows(portrait.get("areaMap"))
    app_years = _sorted_map_rows(portrait.get("applicationYearMap"))
    pub_years = _sorted_map_rows(portrait.get("publicationYearMap"))
    grant_years = _sorted_map_rows(portrait.get("grantYearMap"))
    ipcs = _kv_list_rows(portrait.get("ipcKeyValueList"))
    inventors = _kv_list_rows(portrait.get("inventorKeyValueList"))

    total = sum(c for _, c in legal) if legal else sum(c for _, c in types)
    if total:
        output.append("")
        output.append(f"专利相关统计合计约 **{total:,}** 件（按法律状态汇总）。")

    _append_count_table(output, "法律状态", legal, col_a="法律状态", col_b="件数")
    _append_count_table(output, "专利类型", types, col_a="类型", col_b="件数")
    _append_count_table(output, "布局国家/地区", areas, col_a="国家/地区", col_b="件数")
    _append_count_table(output, "主要 IPC 分类", ipcs, col_a="IPC", col_b="件数")
    _append_count_table(output, "核心发明人（Top）", inventors, col_a="发明人", col_b="件数")
    _append_count_table(output, "申请年趋势", app_years, col_a="申请年", col_b="件数")
    _append_count_table(output, "公开年趋势", pub_years, col_a="公开年", col_b="件数")
    _append_count_table(output, "授权年趋势", grant_years, col_a="授权年", col_b="件数")

    compare = portrait.get("compareMap")
    if isinstance(compare, dict) and compare:
        output.append("")
        output.append("**主要竞争对手（IPC 维度）**")
        for rank in sorted(compare.keys(), key=lambda x: int(x) if str(x).isdigit() else 999):
            output.append(f"- {compare[rank]}")

    if not any([legal, types, areas, ipcs]):
        output.append("")
        output.append("未解析到画像统计数据，请确认企业全称是否正确。")

    output.append("")
    output.append("**您可以继续**")
    output.append(f"- **检索该企业专利**：`applicant:\"{company_name}\"`")
    output.append(f"- **按申请人统计**：对「{company_name}」做 applicant 维度分析")
    output.append("- **查看单件专利**：从检索结果中选公开号查看详情 / 权利要求 / 说明书")
    return "\n".join(output)


def _md_table_cell(text: Any, max_len: int = 80) -> str:
    """GFM 表格单元格：单行、转义竖线。"""
    s = (
        str(text or "")
        .strip()
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", "")
    )
    if max_len and len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s or "-"


def _append_search_usage_hints(
    output: list[str],
    *,
    page: int,
    page_size: int,
    total: int,
    detailed: bool,
    sample_patent_id: str | None = None,
    sort_label: str = "",
) -> None:
    """检索结果末尾：自然语言操作提示（非 API 语法）。"""
    example = (sample_patent_id or "").strip() or "CN112968234A"
    output.append("")
    output.append("**排序方式**（当前：" + (sort_label or "相关度（默认）") + "）")
    output.append("- **按公开日最新**：说「按公开日排序」或「最新公开」")
    output.append("- **按申请日最新**：说「按申请日排序」或「最新申请」")
    output.append("- **按相关度**：说「按相关度排序」")
    output.append("")
    output.append("**您可以继续**")
    if page > 1:
        output.append(f"- **上一页**：说「上一页」或「第 {page - 1} 页」")
    if page * page_size < total:
        output.append(f"- **下一页**：说「下一页」或「第 {page + 1} 页」")
    if not detailed:
        output.append("- **列表加明细**：说「显示详细信息」或「展开摘要和 IPC」")
    else:
        output.append("- **简要列表**：说「简要显示」收起 IPC、摘要列")
    output.append(f"- **专利详情**：如「查看 {example} 的详情」")
    output.append(f"- **权利要求**：如「{example} 的权利要求」")
    output.append(f"- **说明书**：如「{example} 的说明书」")
    output.append(f"- **法律状态**：如「{example} 的法律信息」")
    output.append(f"- **引用 / 相似专利**：如「{example} 的引用」「与 {example} 相似的专利」")
    output.append("- **统计分析**：如「按申请人统计」「按 IPC 或申请年分析」")
    output.append("- **企业专利画像**：如「华为技术有限公司 的企业画像」（需企业全称）")
    output.append(
        "- **全球/多国检索**：说「全球专利」或指定 scope=all / us / jp / kr / tw / wo / ep"
    )
    output.append("- **导出 Excel**：说「导出本次检索结果」")


def _patent_link_label(patent_id: str, portal_url_template: Optional[str]) -> str:
    """表格中的公开号：有 patentUrl 模板时输出 Markdown 链接。"""
    pid = _md_table_cell(patent_id, 22)
    url = build_patent_portal_url(str(patent_id or "").strip(), portal_url_template)
    if url:
        return f"[{pid}]({url})"
    return pid


def _append_patent_detail_hints(output: list[str], patent_id: str) -> None:
    """专利详情末尾：针对当前公开号的后续操作提示。"""
    pid = (patent_id or "").strip() or "CN112968234A"
    output.append("")
    output.append("**您可以继续**")
    output.append(f"- **权利要求**：如「{pid} 的权利要求」")
    output.append(f"- **说明书**：如「{pid} 的说明书」")
    output.append(f"- **法律状态**：如「{pid} 的法律信息」")
    output.append(f"- **引用 / 相似**：如「{pid} 的引用」「与 {pid} 相似的专利」")
    output.append(f"- **摘要附图**：如「{pid} 的附图」或「{pid} 的图片」")
    output.append("- **继续检索**：直接说新的检索式，或「下一页」查看上一检索的后续页")


def format_patent_detail(
    patent_id: str,
    patent: Dict[str, Any],
    *,
    portal_url_template: Optional[str] = None,
    api: Optional["PatentAPI"] = None,
) -> str:
    """专利详情：字段 | 内容 两列表格，摘要单独段落。"""
    pid = patent.get("documentNumber") or patent.get("id") or patent_id
    page_url = None
    if api is not None:
        page_url = api.patent_page_url(str(pid))
    elif portal_url_template:
        page_url = build_patent_portal_url(str(pid), portal_url_template)

    rows: list[tuple[str, Any]] = [
        ("公开号", pid),
        ("标题", patent.get("title")),
        ("申请人", patent.get("applicant")),
        ("发明人", patent.get("inventor")),
        ("代理机构", patent.get("agency")),
        ("申请日", patent.get("applicationDate")),
        ("公开日", patent.get("documentDate")),
        ("IPC 分类", patent.get("ipc")),
        ("主分类", patent.get("mainIpc")),
        ("法律状态", patent.get("legalStatus")),
        ("当前状态", patent.get("currentStatus")),
        ("专利类型", patent.get("type")),
    ]
    if page_url:
        rows.append(("专利网页", f"[在浏览器打开]({page_url})"))

    output = [f"### 专利详情：{patent_id}", "", "| 字段 | 内容 |", "| --- | --- |"]
    for label, raw in rows:
        output.append(f"| {label} | {_md_table_cell(raw, 200)} |")
    summary = _html_to_plain(patent.get("summary", ""))
    if summary:
        output.append("")
        output.append("**摘要**")
        output.append("")
        if len(summary) > 800:
            summary = summary[:800] + "…"
        output.append(summary)

    if api is not None and api.show_patent_images:
        img_md = api.format_patent_images_markdown(patent)
        if img_md:
            output.append("")
            output.append("**摘要附图**")
            output.append("")
            output.append(img_md)
            output.append("")
            output.append(
                "> 附图由 9235 API 提供；若聊天界面不显示图片，可说「下载 CNxxx 附图」保存到本地。"
            )

    _append_patent_detail_hints(output, patent_id)
    return "\n".join(output)


def unescape_patent_text(text: Any) -> str:
    if text is None:
        return ""
    s = str(text)
    return s.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\r")


def _html_to_plain(text: Any) -> str:
    """去除 HTML 标签，保留换行语义。"""
    s = unescape_patent_text(text)
    if not s.strip():
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<p[^>]*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _split_top_level_claims(text: str) -> List[str]:
    """按独立权利要求序号切分（避免误切 IP 等小数）。"""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = unescape_patent_text(text)
    # 仅在「句号/分号 + 换行 + 数字.」或行首「数字.根据/一种」处切分
    parts = re.split(
        r"(?:(?<=[。；])\s*\n\s*(?=\d+\.(?:根据|一种|所述))"
        r"|(?<=\n)(?=\d+\.(?:根据|一种|所述)))",
        text,
    )
    if len(parts) <= 1:
        parts = re.split(r"(?<=[。；])\s*(?=\d+\.(?:根据|一种|所述))", text)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(p)
    return out if out else ([text.strip()] if text.strip() else [])


def format_claims_text(text: Any, max_chars: int = 8000) -> str:
    """格式化权利要求：去 HTML、分条、步骤换行。"""
    s = _html_to_plain(text)
    if not s:
        return ""
    blocks: List[str] = []
    for claim in _split_top_level_claims(s):
        claim = re.sub(r"(步骤[一二三四五六七八九十\d]+[：:])", r"\n\1", claim)
        claim = re.sub(r"\n{2,}", "\n", claim).strip()
        lines = [ln.strip() for ln in claim.split("\n") if ln.strip()]
        blocks.append("\n".join(lines))
    result = "\n\n".join(blocks)
    if max_chars and len(result) > max_chars:
        result = result[:max_chars].rstrip() + "\n\n…（内容已截断，完整全文请至官网查看）"
    return result


def format_description_text(text: Any, max_chars: int = 12000) -> str:
    """格式化说明书：去 HTML、章节标题、段落号 [0001] 分行。"""
    s = _html_to_plain(text)
    if not s:
        return ""
    sec_pat = "|".join(re.escape(x) for x in _DESC_SECTIONS)
    # 章节名后接 [0001] 段落号（最常见）
    s = re.sub(
        rf"({sec_pat})\s*(\[\d{{4}}\])",
        r"\n\n【\1】\n\2 ",
        s,
    )
    # 其余段落号单独成行
    s = re.sub(r"\[(\d{4})\]\s*", r"\n\n[\1] ", s)
    # 优选的 / 实施例 等小标题换行
    s = re.sub(r"(?<=[。；])\s*(?=[一二三四五六七八九十]+、)", r"\n", s)
    s = re.sub(r"(?<=[。；])\s*(?=优选的，)", r"\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    result = s.strip()
    if max_chars and len(result) > max_chars:
        result = result[:max_chars].rstrip() + "\n\n…（内容已截断，完整全文请至官网查看）"
    return result


class PatentAPI:
    """专利API客户端"""
    
    def __init__(
        self,
        token: Optional[str] = None,
        base_url: str = "https://www.9235.net/api",
        *,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化API客户端
        
        Args:
            token: API Token，如果为None则尝试从环境变量或配置文件读取
            base_url: API基础URL
            config: 可选，覆盖 config.json
        """
        cfg = dict(config or load_patent_skill_config())
        self.base_url = resolve_patent_api_base_url(base_url, cfg)

        # 获取token的优先级: 参数 > 环境变量 > 配置文件
        self.token = token
        if not self.token:
            self.token = (
                os.environ.get("PATENT_API_TOKEN")
                or os.environ.get("MCHAT_SKILL_PATENT_SEARCH_PATENT_API_TOKEN")
                or cfg.get("token")
            )

        if not self.token:
            raise ValueError("未找到API Token，请设置环境变量 PATENT_API_TOKEN 或创建配置文件")

        tpl = (
            os.environ.get("PATENT_URL_TEMPLATE")
            or os.environ.get("PATENT_PORTAL_URL_TEMPLATE")
            or cfg.get("patentUrl")
            or cfg.get("patent_url")
            or cfg.get("patent_portal_url_template")
        )
        self.patent_url_template = normalize_patent_url_template(tpl)
        show_img = cfg.get("show_patent_images")
        if show_img is None:
            show_img = os.environ.get("PATENT_SHOW_IMAGES", "1")
        self.show_patent_images = _coerce_bool(show_img, default=True)
        self.download_dir = str(
            os.environ.get("PATENT_DOWNLOAD_DIR")
            or cfg.get("download_dir")
            or "./downloads"
        )

    def patent_page_url(self, patent_id: str) -> Optional[str]:
        return build_patent_portal_url(patent_id, self.patent_url_template)

    @staticmethod
    def extract_image_keys(patent: Dict[str, Any]) -> List[str]:
        keys: List[str] = []
        for field in ("imagePath", "image_path", "thumbImagePath"):
            raw = patent.get(field)
            if raw and str(raw).strip():
                keys.append(str(raw).strip())
        drawings = patent.get("drawings")
        if isinstance(drawings, list):
            for d in drawings:
                if isinstance(d, dict):
                    p = d.get("path") or d.get("key") or d.get("url")
                    if p:
                        keys.append(str(p).strip())
                elif d:
                    keys.append(str(d).strip())
        # 去重保序
        seen: set[str] = set()
        out: List[str] = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out

    def image_api_url(self, image_key: str) -> str:
        """9235 附图接口：GET /api/img?key=...&t=...&v=1"""
        key = (image_key or "").strip()
        if key.startswith("http://") or key.startswith("https://"):
            return key
        return f"{self.base_url}/img?key={quote(key, safe='/')}&t={self.token}&v=1"

    def format_patent_images_markdown(self, patent: Dict[str, Any]) -> str:
        lines: List[str] = []
        for i, key in enumerate(self.extract_image_keys(patent)):
            url = self.image_api_url(key)
            label = "摘要附图" if i == 0 else f"附图 {i + 1}"
            lines.append(f"![{label}]({url})")
        return "\n".join(lines)

    def fetch_image_bytes(self, image_key: str) -> Optional[bytes]:
        try:
            resp = requests.get(self.image_api_url(image_key), timeout=60)
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception:
            pass
        return None

    def _make_request(self, endpoint: str, params: Dict[str, Any] = None, method: str = 'GET') -> Dict[str, Any]:
        """
        发送API请求
        
        Args:
            endpoint: API端点
            params: 请求参数
            method: 请求方法
            
        Returns:
            API响应数据
        """
        if params is None:
            params = {}
        
        # 添加token和版本号
        params['t'] = self.token
        params['v'] = 1
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, params=params, timeout=30)
            else:
                response = requests.post(url, json=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "success": False,
                    "errorCode": response.status_code,
                    "message": f"HTTP {response.status_code}: {response.text[:200]}"
                }
                
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "errorCode": 408,
                "message": "请求超时"
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "errorCode": 503,
                "message": "连接失败"
            }
        except Exception as e:
            return {
                "success": False,
                "errorCode": 500,
                "message": f"请求异常: {str(e)}"
            }
    
    def search(self, query: str, page: int = 1, page_size: int = 10, 
               data_scope: str = "cn", sort: str = "relation") -> Dict[str, Any]:
        """
        搜索专利
        
        Args:
            query: 检索式
            page: 页码
            page_size: 每页条数
            data_scope: 数据范围 (cn/all)
            sort: 排序字段
            
        Returns:
            搜索结果
        """
        params = {
            "ds": _normalize_data_scope(data_scope),
            "q": query,
            "p": page,
            "ps": page_size,
        }
        # 9235 检索接口排序参数为 s（见 SearchApiController）
        api_sort = (sort or "").strip()
        if api_sort:
            params["s"] = api_sort
        return self._make_request("/s", params)
    
    def format_search_result(
        self,
        result: Dict[str, Any],
        detailed: bool = False,
        *,
        page: int = 1,
        page_size: int = 10,
        portal_url_template: Optional[str] = None,
        sort_label: str = "",
    ) -> str:
        """
        格式化搜索结果（Markdown 表格，便于聊天界面展示）
        """
        tpl = portal_url_template if portal_url_template is not None else self.patent_url_template
        page = max(1, int(page or 1))
        page_size = max(1, int(page_size or 10))
        if not result.get("success"):
            return f"❌ 搜索失败: {result.get('message', '未知错误')}"

        patents = result.get("patents", [])
        total = result.get("total", 0)

        output: list[str] = []
        sort_note = sort_label or "相关度（默认）"
        output.append(f"🔍 搜索完成 · 共 **{total:,}** 条 · 第 **{page}** 页")
        output.append(f"📅 排序：**{sort_note}**")
        if not patents:
            output.append("")
            output.append("未找到相关专利")
            return "\n".join(output)

        output.append("")
        if detailed:
            output.append(
                "| 序号 | 专利号 | 标题 | 申请人 | 申请日 | 公开日 | IPC | 摘要 |"
            )
            output.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        else:
            output.append("| 序号 | 专利号 | 标题 | 申请人 | 申请日 | 公开日 |")
            output.append("| --- | --- | --- | --- | --- | --- |")

        for i, patent in enumerate(patents[:10], 1):
            pid = patent.get("id", "未知")
            title = patent.get("title", "未知标题")
            applicant = patent.get("applicant", "未知")
            app_date = patent.get("applicationDate") or "-"
            doc_date = patent.get("documentDate") or "-"
            pid_cell = _patent_link_label(pid, tpl)
            if detailed:
                ipc = patent.get("ipc", "-")
                summary = patent.get("summary", "")
                row = (
                    f"| {i} | {pid_cell} | {_md_table_cell(title, 36)} "
                    f"| {_md_table_cell(applicant, 20)} | {_md_table_cell(app_date, 12)} "
                    f"| {_md_table_cell(doc_date, 12)} "
                    f"| {_md_table_cell(ipc, 16)} | {_md_table_cell(summary, 40)} |"
                )
            else:
                row = (
                    f"| {i} | {pid_cell} | {_md_table_cell(title, 40)} "
                    f"| {_md_table_cell(applicant, 20)} | {_md_table_cell(app_date, 12)} "
                    f"| {_md_table_cell(doc_date, 12)} |"
                )
            output.append(row)

        sample_id = None
        if patents:
            first = patents[0]
            sample_id = str(first.get("id") or first.get("documentNumber") or "").strip() or None

        _append_search_usage_hints(
            output,
            page=page,
            page_size=page_size,
            total=total,
            detailed=detailed,
            sample_patent_id=sample_id,
            sort_label=sort_label,
        )
        return "\n".join(output)

    def format_patent_detail(self, patent_id: str, patent: Dict[str, Any]) -> str:
        return format_patent_detail(patent_id, patent, api=self)

    def format_company_portrait(self, company_name: str, result: Dict[str, Any]) -> str:
        portrait = result.get("enterprisePortrait") or result.get("enterprise_portrait")
        if not isinstance(portrait, dict):
            portrait = {}
        return format_company_portrait(company_name, portrait)
    
    def get_patent_base(self, patent_id: str) -> Dict[str, Any]:
        """
        获取专利基本信息
        
        Args:
            patent_id: 专利ID
            
        Returns:
            专利基本信息
        """
        params = {
            "id": patent_id
        }
        
        return self._make_request("/patent/base", params)
    
    def get_patent_claims(self, patent_id: str) -> Dict[str, Any]:
        """
        获取专利权利要求
        
        Args:
            patent_id: 专利ID
            
        Returns:
            专利权利要求
        """
        params = {
            "id": patent_id
        }
        
        return self._make_request("/patent/claims", params)
    
    def get_patent_desc(self, patent_id: str) -> Dict[str, Any]:
        """
        获取专利说明书
        
        Args:
            patent_id: 专利ID
            
        Returns:
            专利说明书
        """
        params = {
            "id": patent_id
        }
        
        return self._make_request("/patent/desc", params)
    
    def get_patent_tx(self, patent_id: str) -> Dict[str, Any]:
        """
        获取专利法律信息
        
        Args:
            patent_id: 专利ID
            
        Returns:
            专利法律信息
        """
        params = {
            "id": patent_id
        }
        
        return self._make_request("/patent/tx", params)
    
    def get_patent_citing(self, patent_id: str) -> Dict[str, Any]:
        """
        获取专利引用分析
        
        Args:
            patent_id: 专利ID
            
        Returns:
            专利引用分析
        """
        params = {
            "id": patent_id
        }
        
        return self._make_request("/patent/citing", params)
    
    def get_patent_like(self, patent_id: str) -> Dict[str, Any]:
        """
        获取相似专利
        
        Args:
            patent_id: 专利ID
            
        Returns:
            相似专利列表
        """
        params = {
            "id": patent_id
        }
        
        return self._make_request("/patent/like", params)

    def get_patent_family(self, patent_id: str) -> Dict[str, Any]:
        """
        获取专利同族（简单同族，与网站同族页一致，基于 globalpat_family 索引）

        Args:
            patent_id: 专利公开号 / UDN

        Returns:
            patentFamilyList、familyType、total 等
        """
        params = {"id": patent_id}
        return self._make_request("/patent/family", params)
    
    def get_analysis(self, query: str, dimension: str, data_scope: str = "cn") -> Dict[str, Any]:
        """
        获取统计分析
        
        Args:
            query: 检索式
            dimension: 分析维度
            data_scope: 数据范围
            
        Returns:
            统计分析结果
        """
        params = {
            "ds": _normalize_data_scope(data_scope),
            "q": query,
            "field": dimension,
            "column": "trend",
            "ipcLevel": "3",
        }
        return self._make_request("/ration/analysis", params)

    def format_analysis(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析统计分析响应（mchat 下勿 from patent_api import）。"""
        return parse_analysis_items(result)

    @staticmethod
    def error_message(result: Dict[str, Any]) -> str:
        return api_error_message(result)

    @staticmethod
    def result_ok(result: Dict[str, Any]) -> bool:
        return api_result_ok(result)

    @staticmethod
    def unwrap_patent(result: Dict[str, Any]) -> Dict[str, Any]:
        return patent_payload(result)

    @staticmethod
    def decode_text(text: Any) -> str:
        return unescape_patent_text(text)

    @staticmethod
    def format_claims_text(text: Any, max_chars: int = 8000) -> str:
        return format_claims_text(text, max_chars=max_chars)

    @staticmethod
    def format_description_text(text: Any, max_chars: int = 12000) -> str:
        return format_description_text(text, max_chars=max_chars)
    
    def get_company_portrait(self, company_name: str) -> Dict[str, Any]:
        """
        获取企业画像
        
        Args:
            company_name: 企业名称
            
        Returns:
            企业画像数据
        """
        params = {
            "en": company_name
        }
        
        return self._make_request("/a/portrait", params)
    
    def search_copyright(self, query: str, copyright_type: str = "software", 
                        field: str = None, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """
        搜索著作权
        
        Args:
            query: 检索式
            copyright_type: 著作权类型 (software/works)
            field: 查询字段
            page: 页码
            page_size: 每页条数
            
        Returns:
            著作权搜索结果
        """
        params = {
            "q": query,
            "p": page,
            "ps": page_size
        }
        
        if field:
            params["c"] = field
        
        endpoint = "/cr/s" if copyright_type == "software" else "/works/s"
        return self._make_request(endpoint, params)
    
    def search_trademark(self, query: str, page: int = 1, page_size: int = 10, 
                        sort: str = None) -> Dict[str, Any]:
        """
        搜索商标
        
        Args:
            query: 检索式
            page: 页码
            page_size: 每页条数
            sort: 排序字段
            
        Returns:
            商标搜索结果
        """
        params = {
            "q": query,
            "p": page,
            "ps": page_size
        }
        
        if sort:
            params["s"] = sort
        
        return self._make_request("/tm/s", params)
    
    def get_trademark_detail(self, trademark_id: str) -> Dict[str, Any]:
        """
        获取商标详情
        
        Args:
            trademark_id: 商标ID
            
        Returns:
            商标详情
        """
        params = {
            "id": trademark_id
        }
        
        return self._make_request("/tm/base", params)
    
    def download_pdf(self, pdf_path: str, output_dir: str = "./downloads") -> bool:
        """
        下载PDF文件
        
        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录
            
        Returns:
            是否下载成功
        """
        try:
            # 创建输出目录
            os.makedirs(output_dir, exist_ok=True)
            
            # 构建完整URL
            pdf_url = f"{self.base_url}/pdf?path={pdf_path}&t={self.token}"
            
            # 下载文件
            response = requests.get(pdf_url, timeout=60)
            
            if response.status_code == 200:
                # 提取文件名
                filename = os.path.basename(pdf_path)
                if not filename.endswith('.pdf'):
                    filename += '.pdf'
                
                # 保存文件
                output_path = os.path.join(output_dir, filename)
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                
                return True
            else:
                return False
                
        except Exception as e:
            print(f"下载失败: {str(e)}")
            return False
    
    def download_image(self, image_path: str, output_dir: Optional[str] = None) -> bool:
        """
        下载附图（9235 使用 GET /api/img?key=...，非 path=）。
        """
        out_dir = output_dir or self.download_dir
        data = self.fetch_image_bytes(image_path)
        if not data:
            return False
        try:
            os.makedirs(out_dir, exist_ok=True)
            filename = os.path.basename(str(image_path).strip()) or "patent.jpg"
            if not any(filename.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp")):
                filename += ".jpg"
            output_path = os.path.join(out_dir, filename)
            with open(output_path, "wb") as f:
                f.write(data)
            return True
        except OSError:
            return False

# 单例模式支持
_patent_api = None

def get_patent_api() -> PatentAPI:
    """
    获取PatentAPI单例实例
    
    Returns:
        PatentAPI实例
    """
    global _patent_api
    
    if _patent_api is None:
        # 尝试从配置文件读取token
        config_path = Path(__file__).parent / 'config.json'
        token = None
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    token = config.get('token')
            except:
                pass
        
        _patent_api = PatentAPI(token=token)
    
    return _patent_api

if __name__ == '__main__':
    # 测试代码
    try:
        api = get_patent_api()
        
        # 测试搜索
        print("🔍 测试搜索功能...")
        result = api.search("无人机", page_size=3)
        
        if result.get('success'):
            print("✅ 搜索测试成功")
            print(f"📊 找到 {result.get('total', 0)} 条专利")
            
            # 测试格式化输出
            formatted = api.format_search_result(result)
            print("\n📄 搜索结果示例:")
            print(formatted[:500] + "..." if len(formatted) > 500 else formatted)
            
            # 测试获取详情（如果有专利）
            patents = result.get('patents', [])
            if patents:
                patent_id = patents[0]['id']
                print(f"\n🔍 测试获取专利详情: {patent_id}")
                detail = api.get_patent_base(patent_id)
                
                if detail.get('success'):
                    print("✅ 专利详情获取成功")
                    patent = detail.get('patent', {})
                    print(f"📝 标题: {patent.get('title', '未知')[:50]}...")
                    print(f"👤 申请人: {patent.get('applicant', '未知')}")
                else:
                    print(f"❌ 专利详情获取失败: {detail.get('message', '未知错误')}")
        else:
            print(f"❌ 搜索测试失败: {result.get('message', '未知错误')}")
            
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {str(e)}")
        print("\n💡 可能的原因:")
        print("1. 未配置API Token")
        print("2. 网络连接问题")
        print("3. API服务不可用")
        
        print("\n🔧 解决方案:")
        print("1. 设置环境变量: export PATENT_API_TOKEN='您的Token'")
        print("2. 创建配置文件: config.json")
        print("3. 检查网络连接")