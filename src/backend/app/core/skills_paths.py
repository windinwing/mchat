"""Resolve one or more skill package roots (platform + optional external dirs)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings

# Canonical skill ids used by built-in patent workflow templates / presets.
PATENT_SHOWCASE_SEARCH_SKILL = "patent-search"
PATENT_SHOWCASE_REPORT_SKILL = "patent-report"


def resolve_skills_root(raw: str | None = None) -> Path:
    """Return absolute skills root (relative paths resolve from process cwd)."""
    value = (raw if raw is not None else settings.skills_dir or "").strip()
    if not value:
        value = "../../skills"
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return path


def parse_extra_skills_dirs(raw: str | None = None) -> list[Path]:
    """Comma- or colon-separated extra skill roots (e.g. external patent repo)."""
    text = (raw if raw is not None else settings.extra_skills_dirs or "").strip()
    if not text:
        return []
    parts = [p.strip() for chunk in text.split(",") for p in chunk.split(":")]
    roots: list[Path] = []
    seen: set[Path] = set()
    for part in parts:
        if not part:
            continue
        path = Path(part).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        else:
            path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        roots.append(path)
    return roots


def iter_skills_roots() -> list[Path]:
    """Primary SKILLS_DIR first, then EXTRA_SKILLS_DIRS (deduped, order preserved)."""
    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in (resolve_skills_root(), *parse_extra_skills_dirs()):
        if candidate in seen:
            continue
        seen.add(candidate)
        roots.append(candidate)
    return roots


def resolve_skill_directory(skill_name: str) -> Path | None:
    """Find skill package directory by name across all configured roots."""
    name = (skill_name or "").strip()
    if not name:
        return None
    for root in iter_skills_roots():
        if not root.is_dir():
            continue
        skill_md = root / name / "SKILL.md"
        if skill_md.is_file():
            return (root / name).resolve()
    return None
