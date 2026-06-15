"""Tokenization for keyword / BM25 retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CJK_TOKEN = re.compile(r"[\w一-鿿]+", re.UNICODE)

# Built-in stop words when per-KB list is empty (Chinese QA + common English).
DEFAULT_STOP_WORDS: frozenset[str] = frozenset(
    {
        "是什么",
        "什么",
        "怎么",
        "如何",
        "为什么",
        "哪些",
        "哪个",
        "请问",
        "告诉",
        "介绍",
        "一下",
        "关于",
        "简单",
        "说说",
        "讲讲",
        "详细",
        "具体",
        "的",
        "了",
        "在",
        "有",
        "和",
        "与",
        "或",
        "及",
        "等",
        "也",
        "都",
        "就",
        "还",
        "把",
        "被",
        "让",
        "给",
        "对",
        "从",
        "到",
        "为",
        "the",
        "is",
        "are",
        "was",
        "were",
        "a",
        "an",
        "what",
        "how",
        "why",
        "which",
        "who",
        "when",
        "where",
    }
)

DEFAULT_QUERY_SUFFIX_CHARS: frozenset[str] = frozenset("呢吗啊呀吧么")


@dataclass(frozen=True)
class TokenizeConfig:
    stop_words: frozenset[str] = DEFAULT_STOP_WORDS
    query_suffix_chars: frozenset[str] = DEFAULT_QUERY_SUFFIX_CHARS
    user_dict: frozenset[str] = frozenset()

    @classmethod
    def from_kb_fields(
        cls,
        *,
        stop_words_text: str | None = None,
        query_suffix_chars_text: str | None = None,
        user_dict_text: str | None = None,
    ) -> TokenizeConfig:
        extra_stop = parse_word_list(stop_words_text)
        stop_words = DEFAULT_STOP_WORDS | extra_stop if extra_stop else DEFAULT_STOP_WORDS

        suffix_chars = parse_char_list(query_suffix_chars_text)
        if not suffix_chars:
            suffix_chars = DEFAULT_QUERY_SUFFIX_CHARS

        user_dict = parse_word_list(user_dict_text)
        return TokenizeConfig(
            stop_words=stop_words,
            query_suffix_chars=suffix_chars,
            user_dict=user_dict,
        )


def parse_word_list(text: str | None) -> frozenset[str]:
    if not text or not str(text).strip():
        return frozenset()
    words: set[str] = set()
    for line in str(text).replace(",", "\n").replace(";", "\n").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        token = raw.lower()
        if token:
            words.add(token)
    return frozenset(words)


def parse_char_list(text: str | None) -> frozenset[str]:
    if not text or not str(text).strip():
        return frozenset()
    return frozenset(ch for ch in str(text).strip() if not ch.isspace())


def _is_cjk_char(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def _strip_trailing_query_suffix(token: str, suffix_chars: frozenset[str]) -> str:
    out = token
    while out and out[-1] in suffix_chars:
        out = out[:-1]
    return out


def _inject_user_dict_tokens(text: str, user_dict: frozenset[str]) -> set[str]:
    if not user_dict:
        return set()
    lower = (text or "").lower()
    found: set[str] = set()
    for term in sorted(user_dict, key=len, reverse=True):
        if term in lower:
            found.add(term)
    return found


def tokenize_for_search(
    text: str,
    config: TokenizeConfig | None = None,
    *,
    apply_stop_words: bool = True,
) -> set[str]:
    """Tokenize text for BM25 / keyword overlap (CJK-aware)."""
    cfg = config or TokenizeConfig()
    tokens: set[str] = set()
    source = (text or "").lower()

    for raw in _CJK_TOKEN.findall(source):
        if len(raw) > 1 or _is_cjk_char(raw):
            tokens.add(raw)
        stem = _strip_trailing_query_suffix(raw, cfg.query_suffix_chars)
        if stem and (len(stem) > 1 or _is_cjk_char(stem)):
            tokens.add(stem)

    tokens.update(_inject_user_dict_tokens(source, cfg.user_dict))

    if apply_stop_words and cfg.stop_words:
        tokens = {t for t in tokens if t not in cfg.stop_words}

    return tokens
