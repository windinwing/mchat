#!/usr/bin/env python3
"""Seed tenant1 + Pro container channel for local sidecar testing."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.security import get_password_hash
from app.models.customer import CustomerConfig
from app.models.skill import Skill
from app.models.user import User
from app.workspace.paths import tenant_skills_dir


TENANT_USERNAME = "tenant1"
TENANT_PASSWORD = "tenant123"
CHANNEL_NAME = "Tenant1 容器测试助手"
SKILL_NAME = "hello-tenant"


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(User).where(User.username == TENANT_USERNAME)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                username=TENANT_USERNAME,
                password_hash=get_password_hash(TENANT_PASSWORD),
                role="agent",
                display_name="Tenant1 测试",
                workspace_container_allowed=True,
            )
            db.add(user)
            await db.flush()
            print(f"✅ Created user {TENANT_USERNAME} / {TENANT_PASSWORD}")
        else:
            user.workspace_container_allowed = True
            print(f"ℹ️  User {TENANT_USERNAME} exists — container policy set to allow")

        result = await db.execute(
            select(CustomerConfig).where(
                CustomerConfig.user_id == user.id,
                CustomerConfig.name == CHANNEL_NAME,
            )
        )
        channel = result.scalar_one_or_none()
        ends = datetime.now(timezone.utc) + timedelta(days=365)
        if channel is None:
            channel = CustomerConfig(
                name=CHANNEL_NAME,
                user_id=user.id,
                plan="pro",
                workspace_mode="container",
                enabled=True,
                subscription_ends_at=ends,
                welcome_message="Tenant1 容器测试通道",
            )
            db.add(channel)
            await db.flush()
            print(f"✅ Created channel: {CHANNEL_NAME} ({channel.id})")
        else:
            channel.plan = "pro"
            channel.workspace_mode = "container"
            channel.enabled = True
            channel.subscription_ends_at = ends
            print(f"ℹ️  Updated channel: {CHANNEL_NAME} ({channel.id})")

        skill_dir = tenant_skills_dir(user.id) / SKILL_NAME
        skill_dir.mkdir(parents=True, exist_ok=True)
        main_py = skill_dir / "main.py"
        skill_md = skill_dir / "SKILL.md"
        if not main_py.is_file():
            main_py.write_text(
                'def run(**kwargs):\n'
                '    name = kwargs.get("name", "tenant1")\n'
                '    return {"message": f"Hello {name} from sidecar", "args": kwargs}\n',
                encoding="utf-8",
            )
        if not skill_md.is_file():
            skill_md.write_text(
                f"---\nname: {SKILL_NAME}\ndescription: Tenant sidecar smoke test\n---\n",
                encoding="utf-8",
            )

        result = await db.execute(
            select(Skill).where(
                Skill.user_id == user.id,
                Skill.name == SKILL_NAME,
            )
        )
        skill = result.scalar_one_or_none()
        skill_path = str(main_py.resolve())
        if skill is None:
            skill = Skill(
                user_id=user.id,
                name=SKILL_NAME,
                description="Sidecar smoke test skill",
                skill_type="tool",
                path=skill_path,
                config={"origin": "tenant"},
                enabled=True,
            )
            db.add(skill)
            print(f"✅ Registered skill {SKILL_NAME}")
        else:
            skill.path = skill_path
            skill.enabled = True
            skill.config = {**(skill.config or {}), "origin": "tenant"}
            print(f"ℹ️  Skill {SKILL_NAME} already registered")

        await db.commit()

        # Register platform skills (requires SKILLS_DIR=../../skills in .env)
        from app.services.skill_service import SkillService
        from app.core.skills_paths import resolve_skill_directory
        from app.workspace.skill_sync import sync_skill_directory_to_tenant

        svc = SkillService(db)
        platform_skills = ("mchat-help", "patent-search", "patent-report", "wheelchair-advisor")
        tenant_dir = tenant_skills_dir(user.id)
        for name in platform_skills:
            src = resolve_skill_directory(name)
            if src is not None:
                sync_skill_directory_to_tenant(src, tenant_dir)
        await svc.reload_skills(user.id)
        skill_rows = await svc.list_skills(user.id)
        by_name = {s.name: s.id for s in skill_rows}
        channel.skill_ids = [by_name[n] for n in platform_skills if n in by_name]
        await db.commit()

        print("")
        print("Test credentials:")
        print(f"  username: {TENANT_USERNAME}")
        print(f"  password: {TENANT_PASSWORD}")
        print(f"  user_id:  {user.id}")
        print(f"  channel:  {channel.id}")
        print(f"  tenant:   {settings.workspace_root_dir}/{user.id}/")
        print("")
        print("Login: http://localhost:5173/admin")
        print("Skills: http://localhost:5173/admin/skills")
        print("Workspace: http://localhost:5173/admin/workspace")


if __name__ == "__main__":
    asyncio.run(main())
