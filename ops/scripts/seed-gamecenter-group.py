#!/usr/bin/env python3
"""Register DevBridge dev skills and bind them to a group's default_skill_ids."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.group import Group
from app.models.user import User
from app.services.skill_service import SkillService

DEFAULT_DEV_SKILLS = (
    "gamecenter-dev-agent",
    "dev-assistant",
    "git-commit-writer",
    "code-reviewer",
)


async def main(
    username: str,
    group_name: str | None,
    project_slugs: list[str],
    skill_names: list[str],
) -> None:
    async with async_session_factory() as db:
        user = (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if user is None:
            print(f"❌ User not found: {username}")
            sys.exit(1)

        svc = SkillService(db)
        await svc.reload_skills(user.id)
        skills = await svc.list_skills(user.id)
        by_name = {s.name: s for s in skills}

        missing = [name for name in skill_names if name not in by_name]
        if missing:
            print(f"❌ Skills not found after reload: {', '.join(missing)}")
            print("   Ensure skills/ contains them, then retry.")
            sys.exit(1)

        query = select(Group).order_by(Group.created_at.asc())
        if group_name:
            query = select(Group).where(Group.name == group_name)
        group = (await db.execute(query)).scalars().first()
        if group is None:
            print("❌ No group found" + (f" with name {group_name!r}" if group_name else ""))
            sys.exit(1)

        ids = list(group.default_skill_ids or [])
        for name in skill_names:
            skill = by_name[name]
            if skill.id not in ids:
                ids.append(skill.id)
        group.default_skill_ids = ids
        if project_slugs:
            group.devbridge_project_allowlists = {"gamecenter": project_slugs}
            group.gamecenter_project_allowlist = None
        await db.commit()
        print(f"✅ Group {group.name!r} default skills: {', '.join(skill_names)}")
        if project_slugs:
            print(f"✅ devbridge_project_allowlists.gamecenter = {project_slugs}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="admin", help="Skill owner username (default: admin)")
    parser.add_argument("--group", default=None, help="Group name (default: first group)")
    parser.add_argument(
        "--projects",
        default="",
        help="Comma-separated GameCenter project slugs for allowlist (empty = skip)",
    )
    parser.add_argument(
        "--skills",
        default=",".join(DEFAULT_DEV_SKILLS),
        help=f"Comma-separated skill names (default: {','.join(DEFAULT_DEV_SKILLS)})",
    )
    args = parser.parse_args()
    slugs = [s.strip() for s in (args.projects or "").split(",") if s.strip()]
    skill_names = [s.strip() for s in (args.skills or "").split(",") if s.strip()]
    asyncio.run(main(args.user, args.group, slugs, skill_names))
