"""Text chunking strategies for knowledge base documents."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

ChunkStrategy = Literal["fixed", "paragraph", "markdown", "semantic"]


@dataclass(frozen=True)
class ChunkConfig:
    strategy: ChunkStrategy = "fixed"
    size: int = 500
    overlap: int = 50
    min_chunk_size: int = 80
    max_chunk_size: int = 2000
    semantic_threshold: float = 0.7
    parent_max_ratio: int = 3

    def normalized(self) -> ChunkConfig:
        size = max(100, min(self.size, self.max_chunk_size))
        overlap = max(0, min(self.overlap, size // 2))
        return ChunkConfig(
            strategy=self.strategy,
            size=size,
            overlap=overlap,
            min_chunk_size=max(20, self.min_chunk_size),
            max_chunk_size=self.max_chunk_size,
            semantic_threshold=max(0.5, min(0.95, self.semantic_threshold)),
            parent_max_ratio=max(2, min(5, self.parent_max_ratio)),
        )


def chunk_text(text: str, config: ChunkConfig | None = None) -> list[str]:
    """Split text using the configured strategy."""
    cfg = (config or ChunkConfig()).normalized()
    text = (text or "").strip()
    if not text:
        return []

    if cfg.strategy == "paragraph":
        return _chunk_paragraph(text, cfg)
    if cfg.strategy == "markdown":
        return _chunk_markdown(text, cfg)
    if cfg.strategy == "semantic":
        return _chunk_fixed(text, cfg)  # fallback: embedder required, caller handles
    return _chunk_fixed(text, cfg)


def chunk_text_with_parents(
    text: str,
    config: ChunkConfig | None = None,
    embedder=None,
) -> list[tuple[str, str | None]]:
    """Return (child_content, parent_content) pairs for parent-child indexing.

    For non-semantic strategies, parent is always None.
    For semantic strategy, parent is a larger context window around the child.
    """
    cfg = (config or ChunkConfig()).normalized()
    text = (text or "").strip()
    if not text:
        return []

    if cfg.strategy == "semantic" and embedder is not None:
        return _chunk_semantic(text, cfg, embedder)

    # Non-semantic: children only, no parent
    children = chunk_text(text, cfg)
    return [(c, None) for c in children]


def _chunk_fixed(text: str, cfg: ChunkConfig) -> list[str]:
    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + cfg.size, text_len)

        if end < text_len:
            paragraph_break = text.rfind("\n\n", start, end)
            if paragraph_break > start:
                end = paragraph_break + 2
            else:
                for sep in (". ", "! ", "? ", ".\n", "\n"):
                    pos = text.rfind(sep, start, end)
                    if pos > start:
                        end = pos + len(sep)
                        break

        piece = text[start:end].strip()
        if len(piece) >= cfg.min_chunk_size or (not chunks and piece):
            chunks.append(piece)
        elif piece and chunks:
            chunks[-1] = f"{chunks[-1]}\n\n{piece}"[: cfg.max_chunk_size]

        if end >= text_len:
            break
        # Guarantee forward progress: a separator found right after `start`
        # (e.g. "\n\n" at start+1) makes `end` advance by only a few chars, so
        # subtracting the overlap can move `start` backwards and loop forever.
        # Always advance at least one char past the previous start.
        start = max(end - cfg.overlap, start + 1)

    return [c for c in chunks if c]


def _chunk_paragraph(text: str, cfg: ChunkConfig) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    buffer = ""

    for para in paragraphs:
        if len(para) > cfg.max_chunk_size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_chunk_fixed(para, cfg))
            continue

        candidate = f"{buffer}\n\n{para}".strip() if buffer else para
        if len(candidate) <= cfg.size:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = para

    if buffer:
        chunks.append(buffer)

    return _merge_small_chunks(chunks, cfg.min_chunk_size)


def _chunk_markdown(text: str, cfg: ChunkConfig) -> list[str]:
    sections = re.split(r"(?=^#{1,6}\s)", text, flags=re.MULTILINE)
    sections = [s.strip() for s in sections if s.strip()]
    if not sections:
        return _chunk_fixed(text, cfg)

    chunks: list[str] = []
    for section in sections:
        if len(section) <= cfg.size:
            chunks.append(section)
        else:
            chunks.extend(_chunk_paragraph(section, cfg))

    return _merge_small_chunks(chunks, cfg.min_chunk_size)


def _merge_small_chunks(chunks: list[str], min_size: int) -> list[str]:
    if not chunks:
        return []
    merged: list[str] = []
    for chunk in chunks:
        if merged and len(merged[-1]) < min_size:
            merged[-1] = f"{merged[-1]}\n\n{chunk}"
        else:
            merged.append(chunk)
    return merged


def _split_sentences(text: str) -> list[str]:
    """Split text into sentence-like segments."""
    # Split on sentence-ending punctuation followed by space or newline
    raw = re.split(r"(?<=[。.!！?？\n])(?=\s*\S)", text.strip())
    segments: list[str] = []
    for s in raw:
        s_clean = s.strip()
        if s_clean:
            segments.append(s_clean)
    return segments


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def _detect_boundaries(embeddings: list[list[float]], threshold: float) -> list[int]:
    """Return indices where consecutive embedding similarity drops below threshold."""
    boundaries: list[int] = []
    for i in range(1, len(embeddings)):
        sim = _cosine_sim(embeddings[i - 1], embeddings[i])
        if sim < threshold:
            boundaries.append(i)
    return boundaries


def _chunk_semantic(
    text: str, cfg: ChunkConfig, embedder
) -> list[tuple[str, str | None]]:
    """Semantic chunking: split by topic boundaries, with parent context."""
    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        return [(text, None)]

    try:
        embeddings = embedder.embed_documents(sentences)
    except Exception:
        return [(c, None) for c in _chunk_fixed(text, cfg)]

    boundaries = _detect_boundaries(embeddings, cfg.semantic_threshold)

    # Build child chunks from segments between boundaries
    child_chunks: list[str] = []
    seg_start = 0
    for b in boundaries:
        segment = " ".join(sentences[seg_start:b]).strip()
        if segment:
            child_chunks.append(segment)
        seg_start = b
    last_segment = " ".join(sentences[seg_start:]).strip()
    if last_segment:
        child_chunks.append(last_segment)

    if not child_chunks:
        return [(text, None)]

    # Merge small children
    child_chunks = _merge_small_chunks(
        _chunk_fixed("\n\n".join(child_chunks), cfg), cfg.min_chunk_size
    )
    # But semantic chunks should use the original segment boundaries
    # Re-split if fixed chunking merged them incorrectly
    if len(child_chunks) <= 1:
        return [(c, None) for c in child_chunks]

    # Build parent contexts: for each child, merge with adjacent children up to parent_max_ratio * child size
    result: list[tuple[str, str | None]] = []
    n = len(child_chunks)
    for i, child in enumerate(child_chunks):
        parent = _build_parent(child_chunks, i, cfg)
        result.append((child, parent))

    return result


def _build_parent(chunks: list[str], idx: int, cfg: ChunkConfig) -> str | None:
    """Build a parent context by expanding around the child chunk."""
    child = chunks[idx]
    child_len = len(child)
    max_parent_len = child_len * cfg.parent_max_ratio

    left = idx - 1
    right = idx + 1
    parent_parts = [child]

    while len(" ".join(parent_parts)) < max_parent_len:
        added = False
        if left >= 0 and len(" ".join([chunks[left]] + parent_parts)) <= max_parent_len:
            parent_parts.insert(0, chunks[left])
            left -= 1
            added = True
        if right < len(chunks) and len(" ".join(parent_parts + [chunks[right]])) <= max_parent_len:
            parent_parts.append(chunks[right])
            right += 1
            added = True
        if not added:
            break

    full = " ".join(parent_parts)
    return full if full != child else None
