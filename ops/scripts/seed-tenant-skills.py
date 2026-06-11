#!/usr/bin/env python3
"""Register platform skills for a tenant user (reload from SKILLS_DIR + tenant skills/)."""

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
from app.core.skills_paths import iter_skills_roots
from app.models.customer import CustomerConfig
from app.models.user import User
from app.services.skill_service import SkillService
from app.workspace.skill_sync import sync_skill_directory_to_tenant
from app.workspace.paths import tenant_skills_dir

DEFAULT_SKILLS = (
    "mchat-help",
    "patent-search",
    "patent-report",
    "wheelchair-advisor",
)


async def main(username: str, skill_names: list[str], bind_channel: bool) -> None:
    async with async_session_factory() as db:
        user = (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if user is None:
            print(f"❌ User not found: {username}")
            sys.exit(1)

        print("Skill roots:", ", ".join(str(r) for r in iter_skills_roots()))

        svc = SkillService(db)
        result = await svc.reload_skills(user.id)
        await db.flush()

        tenant_dir = tenant_skills_dir(user.id)
        synced: list[str] = []
        for name in skill_names:
            from app.core.skills_paths import resolve_skill_directory

            src = resolve_skill_directory(name)
            if src is None:
                print(f"⚠ Skip sync (not on disk): {name}")
                continue
            sync_skill_directory_to_tenant(src, tenant_dir)
            synced.append(name)
            print(f"✓ Synced to tenant: {name}")

        if synced:
            await svc.reload_skills(user.id)

        if bind_channel:
            ch = (
                await db.execute(
                    select(CustomerConfig)
                    .where(CustomerConfig.user_id == user.id)
                    .order_by(CustomerConfig.created_at.desc())
                )
            ).scalars().first()
            if ch is not None:
                skill_rows = await svc.list_skills(user.id)
                by_name = {s.name: s.id for s in skill_rows}
                ids = [by_name[n] for n in skill_names if n in by_name]
                if ids:
                    ch.skill_ids = ids
                    print(f"✓ Channel {ch.name!r} skill_ids = {skill_names}")

        await db.commit()
        skills = await svc.list_skills(user.id)
        enabled = [s.name for s in skills if s.enabled]
        print("")
        print(f"✅ {username}: {result['reloaded']} skills in DB, {len(enabled)} enabled")
        print("   ", ", ".join(sorted(enabled)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="tenant1")
    parser.add_argument(
        "--skills",
        nargs="*",
        default=list(DEFAULT_SKILLS),
        help=f"Platform skills to sync (default: {' '.join(DEFAULT_SKILLS)})",
    )
    parser.add_argument(
        "--bind-channel",
        action="store_true",
        help="Attach listed skills to the user's latest channel",
    )
    args = parser.parse_args()
    asyncio.run(main(args.user, args.skills, args.bind_channel))
