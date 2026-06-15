"""Filesystem-backed tokenizer word lists (one entry per line)."""

from __future__ import annotations

import re
from pathlib import Path

from app.utils.upload_paths import resolve_upload_root

_GLOBAL_DIR_NAME = "tokenizer"
_KB_DIR_NAME = "knowledge"

GLOBAL_STOP_WORDS = "stop_words"
GLOBAL_SUFFIX_CHARS = "suffix_chars"
KB_USER_DICT = "user_dict"

_GLOBAL_FILE_NAMES = {
    GLOBAL_STOP_WORDS: "stop_words.txt",
    GLOBAL_SUFFIX_CHARS: "suffix_chars.txt",
}

_KB_FILE_NAMES = {
    KB_USER_DICT: "user_dict.txt",
}

_COMMENT_LINE = re.compile(r"^\s*#")


def _tokenizer_root() -> Path:
    root = resolve_upload_root() / _GLOBAL_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _kb_tokenizer_dir(kb_id: str) -> Path:
    kb_id = (kb_id or "").strip()
    if not kb_id:
        raise ValueError("knowledge_base_id required")
    root = resolve_upload_root() / _KB_DIR_NAME / kb_id / _GLOBAL_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_text_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if content is not None else "", encoding="utf-8")


def list_global_tokenizer_files() -> list[dict[str, str | int]]:
    """Metadata for admin UI."""
    items: list[dict[str, str | int]] = []
    root = _tokenizer_root()
    for key, filename in _GLOBAL_FILE_NAMES.items():
        path = root / filename
        content = _read_text_file(path)
        line_count = len([ln for ln in content.splitlines() if ln.strip() and not _COMMENT_LINE.match(ln)])
        items.append(
            {
                "key": key,
                "filename": filename,
                "path": str(path),
                "line_count": line_count,
            }
        )
    return items


def read_global_tokenizer_file(key: str) -> dict[str, str]:
    filename = _GLOBAL_FILE_NAMES.get(key)
    if not filename:
        raise ValueError(f"Unknown global tokenizer file: {key}")
    path = _tokenizer_root() / filename
    return {
        "key": key,
        "filename": filename,
        "content": _read_text_file(path),
    }


def write_global_tokenizer_file(key: str, content: str) -> dict[str, str]:
    filename = _GLOBAL_FILE_NAMES.get(key)
    if not filename:
        raise ValueError(f"Unknown global tokenizer file: {key}")
    path = _tokenizer_root() / filename
    _write_text_file(path, content)
    return read_global_tokenizer_file(key)


def read_kb_tokenizer_file(kb_id: str, key: str = KB_USER_DICT) -> dict[str, str]:
    filename = _KB_FILE_NAMES.get(key)
    if not filename:
        raise ValueError(f"Unknown knowledge-base tokenizer file: {key}")
    path = _kb_tokenizer_dir(kb_id) / filename
    return {
        "key": key,
        "filename": filename,
        "knowledge_base_id": kb_id,
        "content": _read_text_file(path),
    }


def write_kb_tokenizer_file(kb_id: str, content: str, key: str = KB_USER_DICT) -> dict[str, str]:
    filename = _KB_FILE_NAMES.get(key)
    if not filename:
        raise ValueError(f"Unknown knowledge-base tokenizer file: {key}")
    path = _kb_tokenizer_dir(kb_id) / filename
    _write_text_file(path, content)
    return read_kb_tokenizer_file(kb_id, key=key)


def resolve_tokenizer_texts(kb: object | None) -> tuple[str | None, str | None, str | None]:
    """Return (stop_words, suffix_chars, user_dict) text for a knowledge base."""
    stop_words = read_global_tokenizer_file(GLOBAL_STOP_WORDS)["content"] or None
    suffix_chars = read_global_tokenizer_file(GLOBAL_SUFFIX_CHARS)["content"] or None

    user_dict: str | None = None
    if kb is not None:
        kb_id = str(getattr(kb, "id", "") or "").strip()
        if kb_id:
            file_text = read_kb_tokenizer_file(kb_id)["content"]
            if file_text.strip():
                user_dict = file_text
        if not user_dict:
            legacy = getattr(kb, "retrieval_user_dict", None)
            if legacy and str(legacy).strip():
                user_dict = str(legacy)

    # Legacy per-KB global fields (pre-file migration): only used when global files empty.
    if kb is not None:
        if not (stop_words or "").strip():
            legacy_stop = getattr(kb, "retrieval_stop_words", None)
            if legacy_stop and str(legacy_stop).strip():
                stop_words = str(legacy_stop)
        if not (suffix_chars or "").strip():
            legacy_suffix = getattr(kb, "retrieval_query_suffix_chars", None)
            if legacy_suffix and str(legacy_suffix).strip():
                suffix_chars = str(legacy_suffix)

    return stop_words, suffix_chars, user_dict
