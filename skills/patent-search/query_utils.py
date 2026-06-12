"""Build patent search / analysis query strings."""

from __future__ import annotations

import re
from typing import Optional

YEAR_DIMENSIONS = frozenset(
    {"applicationYear", "documentYear", "grantYear", "publicationYear"}
)

# 9235 检索 API 排序参数名为 s（非 sort）；!field 表示降序
_RECENT_SORT_HINTS = (
    "最新",
    "最近",
    "新近",
    "近期",
    "latest",
    "recent",
    "newest",
)

_APPLICATION_SORT_HINTS = (
    "最新申请",
    "最近申请",
    "申请日最新",
    "按申请日",
    "申请最新",
    "申请日降序",
    "applicationdate",
)

_DOCUMENT_SORT_HINTS = (
    "最新公开",
    "最近公开",
    "公开日最新",
    "最新公告",
    "按公开日",
    "公开最新",
    "公开日降序",
    "最新公布",
    "documentdate",
)

_SORT_ALIASES = {
    "relation": "",
    "date": "!documentDate",
    "latest": "!documentDate",
    "recent": "!documentDate",
    "newest": "!documentDate",
    "applicationdate": "!applicationDate",
    "!applicationdate": "!applicationDate",
    "documentdate": "!documentDate",
    "!documentdate": "!documentDate",
    "申请日": "!applicationDate",
    "公开日": "!documentDate",
    "最新申请": "!applicationDate",
    "最新公开": "!documentDate",
    # Widget action pill 字面消息
    "按最新公开排序": "!documentDate",
    "按最新公布排序": "!documentDate",
    "按最新申请排序": "!applicationDate",
}

SORT_LABELS = {
    "": "相关度（默认）",
    "!applicationDate": "申请日 · 新→旧",
    "applicationDate": "申请日 · 旧→新",
    "!documentDate": "公开日 · 新→旧",
    "documentDate": "公开日 · 旧→新",
}


def sort_display_label(api_sort: Optional[str]) -> str:
    key = (api_sort or "").strip()
    return SORT_LABELS.get(key, key or SORT_LABELS[""])


def infer_sort_from_query(query: str) -> Optional[str]:
    """从用户表述推断排序；泛化「最新」默认按公开日降序。"""
    q = (query or "").strip()
    if not q:
        return None
    ql = q.lower()
    if any(h in q or h in ql for h in _APPLICATION_SORT_HINTS):
        return "!applicationDate"
    if any(h in q or h in ql for h in _DOCUMENT_SORT_HINTS):
        return "!documentDate"
    if any(h in q or h in ql for h in _RECENT_SORT_HINTS):
        return "!documentDate"
    return None


def normalize_patent_sort(sort: Optional[str]) -> str:
    """将 CLI/工具别名映射为 9235 API 的 s 参数值。"""
    s = (sort or "").strip()
    if not s or s == "relation":
        return ""
    alias = _SORT_ALIASES.get(s.lower().replace("-", "_"))
    if alias is not None:
        return alias
    if s.startswith("!") or s in (
        "applicationDate",
        "documentDate",
        "rank",
        "score",
        "relation",
    ):
        return s
    return s


def resolve_search_sort(query: str, sort: Optional[str] = None) -> str:
    """合并显式 sort 与查询语义推断。"""
    explicit = normalize_patent_sort(sort)
    if explicit:
        return explicit
    return normalize_patent_sort(infer_sort_from_query(query)) or ""


def clean_search_query(query: str) -> str:
    """去掉口语前缀和排序后缀，保留检索关键词。"""
    q = (query or "").strip()
    if not q:
        return q
    q = re.sub(r"^请?(帮我)?(查询|搜索|检索|找)(一下)?", "", q, flags=re.I).strip()
    q = re.sub(r"^(最新|最近|新近|近期)(的)?", "", q).strip()
    q = re.sub(r"(的)?(专利|发明|技术方案)(清单|列表|信息)?$", "", q).strip()
    # Strip sort commands: "按最新公开排序", "按最新申请降序", etc.
    q = re.sub(r"(按)?(最新(公开|公布|公告|申请)|(公开|申请|公告)日)(最新|降序|排序)?$", "", q).strip()
    q = re.sub(r"\s+", " ", q).strip(" 的，,")
    # When the entire query is a sort command (clicked action pill)
    return q or ""


def prepare_search_request(
    query: str, sort: Optional[str] = None
) -> tuple[str, str, str]:
    """返回 (检索式, api_sort, 排序说明)。"""
    raw = (query or "").strip()
    api_sort = resolve_search_sort(raw, sort)
    cleaned = clean_search_query(raw)
    if cleaned:
        search_q = cleaned
    elif api_sort:
        # 整句仅为排序指令（如 action pill）；检索词须由 LLM 在 query 中单独传入
        search_q = ""
    else:
        search_q = raw
    return search_q, api_sort, sort_display_label(api_sort)


def build_analysis_query(
    query: str,
    dimension: str | None = None,
    *,
    year_from: str | int | None = None,
    year_to: str | int | None = None,
) -> str:
    """Append year range filter for year-dimension analysis (e.g. applicationYear:[2020 TO 2024])."""
    base = (query or "").strip()
    dim = (dimension or "").strip()
    yf = str(year_from or "").strip()
    yt = str(year_to or "").strip()
    if dim not in YEAR_DIMENSIONS or not yf or not yt:
        return base
    try:
        yf_i, yt_i = int(yf), int(yt)
        if yf_i > yt_i:
            yf_i, yt_i = yt_i, yf_i
        clause = f"{dim}:[{yf_i} TO {yt_i}]"
    except ValueError:
        clause = f"{dim}:[{yf} TO {yt}]"
    if base:
        return f"{clause} AND ({base})"
    return clause
