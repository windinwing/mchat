"""Tests for skill DB cache vs disk status."""

from __future__ import annotations

import pytest

from app.models.skill import Skill
from app.services.skill_service import SkillService


@pytest.mark.asyncio
async def test_list_cache_status_detects_stale_prompt_body(db_session, tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo-skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\nname: demo-skill\ndescription: d\ntype: prompt\n---\n\nDisk body v2\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.skill.loader.iter_skills_roots",
        lambda: [skills_root],
    )
    monkeypatch.setattr(
        "app.workspace.skill_policy.resolve_skill_directory",
        lambda _name: None,
    )

    user_id = "cache-user-1"
    skill = Skill(
        id="sk-cache-1",
        user_id=user_id,
        name="demo-skill",
        skill_type="prompt",
        path=str(skill_md),
        config={"prompt_body": "Old cached body"},
        enabled=True,
    )
    db_session.add(skill)
    await db_session.flush()

    svc = SkillService(db_session)
    status = await svc.list_cache_status(user_id)

    assert status.stale_count == 1
    entry = status.items[0]
    assert entry.prompt_body_stale is True
    assert entry.disk_chars > 0


@pytest.mark.asyncio
async def test_refresh_skill_cache_updates_prompt_body(db_session, tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo-skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    disk_body = "Fresh from disk"
    skill_md.write_text(
        f"---\nname: demo-skill\ndescription: d\ntype: prompt\n---\n\n{disk_body}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.skill.loader.iter_skills_roots",
        lambda: [skills_root],
    )
    monkeypatch.setattr(
        "app.workspace.skill_policy.resolve_skill_directory",
        lambda _name: None,
    )

    user_id = "cache-user-2"
    skill = Skill(
        id="sk-cache-2",
        user_id=user_id,
        name="demo-skill",
        skill_type="prompt",
        path=str(skill_md),
        config={"prompt_body": "stale"},
        enabled=True,
    )
    db_session.add(skill)
    await db_session.flush()

    svc = SkillService(db_session)
    updated = await svc.refresh_skill_cache(skill.id, user_id)

    assert (updated.config or {}).get("prompt_body", "").strip() == disk_body
