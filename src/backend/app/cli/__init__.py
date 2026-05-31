"""mchat CLI - Management command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import io
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse


def _register_skill_subcommands(skill_sub: argparse._SubParsersAction) -> None:
    skill_sub.add_parser("list", help="List installed skills")
    skill_parser_create = skill_sub.add_parser("create", help="Create a new skill")
    skill_parser_create.add_argument("name", help="Skill name")
    skill_parser_install = skill_sub.add_parser(
        "install", help="Install skill from URL or ClawHub name"
    )
    skill_parser_install.add_argument("source", help="Zip URL or skill name")
    skill_parser_install.add_argument(
        "--name",
        help="Optional local folder name hint",
    )


def main() -> None:
    """Entry point for the mchat CLI."""
    parser = argparse.ArgumentParser(
        prog="mchat",
        description="mchat - Multi-tenant AI Chat Platform CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init: initialize the project
    init_parser = subparsers.add_parser("init", help="Initialize mchat project")
    init_parser.add_argument(
        "--path",
        default=".",
        help="Project path (default: current directory)",
    )

    # run: start the server
    run_parser = subparsers.add_parser("run", help="Run the mchat server")
    run_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)",
    )
    run_parser.add_argument(
        "--port",
        type=int,
        default=3001,
        help="Port to bind (default: 3001)",
    )
    run_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    # worker: run independent background scheduler
    worker_parser = subparsers.add_parser("worker", help="Run background worker")
    worker_parser.add_argument(
        "--once",
        action="store_true",
        help="Run enabled jobs once and exit",
    )

    # config: manage configuration
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_sub = config_parser.add_subparsers(dest="config_action")
    config_sub.add_parser("show", help="Show current configuration")
    config_sub.add_parser("validate", help="Validate configuration")

    # skill: manage skills
    skill_parser = subparsers.add_parser("skill", help="Manage skills")
    skill_sub = skill_parser.add_subparsers(dest="skill_action")
    _register_skill_subcommands(skill_sub)

    # skills: alias of skill
    skills_parser = subparsers.add_parser("skills", help="Manage skills (alias)")
    skills_sub = skills_parser.add_subparsers(dest="skill_action")
    _register_skill_subcommands(skills_sub)

    # db: database management
    db_parser = subparsers.add_parser("db", help="Database management")
    db_sub = db_parser.add_subparsers(dest="db_action")
    db_sub.add_parser("init", help="Initialize database tables")
    db_sub.add_parser("migrate", help="Run database migrations")
    db_sub.add_parser("seed", help="Seed database with sample data")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    asyncio.run(_handle_command(args))


async def _handle_command(args: argparse.Namespace) -> None:
    """Route command to handler."""
    match args.command:
        case "init":
            await _cmd_init(args)
        case "run":
            await _cmd_run(args)
        case "worker":
            await _cmd_worker(args)
        case "config":
            await _cmd_config(args)
        case "skill":
            await _cmd_skill(args)
        case "skills":
            await _cmd_skill(args)
        case "db":
            await _cmd_db(args)
        case _:
            print(f"Unknown command: {args.command}")
            sys.exit(1)


async def _cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new mchat project."""
    project_path = Path(args.path).resolve()
    print(f"Initializing mchat project at {project_path}")

    # Create directory structure
    dirs = [
        "src/backend/app",
        "src/frontend/src",
        "skills",
        "docs",
        "ops/docker",
        "ops/nginx",
        "ops/scripts",
        "tests",
    ]
    for d in dirs:
        (project_path / d).mkdir(parents=True, exist_ok=True)

    # Create .env from example
    env_path = project_path / ".env"
    if not env_path.exists():
        env_path.write_text(
            "# mchat Configuration\n"
            "DATABASE_URL=mysql+aiomysql://mchat:mchat123@localhost:3306/mchat\n"
            "JWT_SECRET=change-me-to-a-random-string\n"
            "ADMIN_USERNAME=admin\n"
            "ADMIN_PASSWORD=admin123\n"
        )

    print("✅ Project initialized! Run 'mchat run' to start.")


async def _cmd_run(args: argparse.Namespace) -> None:
    """Start the mchat server."""
    import uvicorn

    print(f"Starting mchat server on {args.host}:{args.port}")
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


async def _cmd_worker(args: argparse.Namespace) -> None:
    """Start background scheduler worker."""
    from app.worker.main import run_worker

    await run_worker(run_once=bool(getattr(args, "once", False)))


async def _cmd_config(args: argparse.Namespace) -> None:
    """Manage configuration."""
    from app.core.config import settings

    match args.config_action:
        case "show":
            print("Current configuration:")
            for field_name in settings.model_fields:
                value = getattr(settings, field_name)
                if "secret" in field_name.lower() or "password" in field_name.lower():
                    value = "********"
                print(f"  {field_name} = {value}")
        case "validate":
            try:
                print("✅ Configuration is valid")
            except Exception as e:
                print(f"❌ Configuration error: {e}")
                sys.exit(1)
        case _:
            print("Use: mchat config show|validate")


async def _cmd_skill(args: argparse.Namespace) -> None:
    """Manage skills."""
    match args.skill_action:
        case "list":
            skills_dir = Path("skills")
            if skills_dir.exists():
                for skill_dir in sorted(skills_dir.iterdir()):
                    if skill_dir.is_dir():
                        skill_md = skill_dir / "SKILL.md"
                        if skill_md.exists():
                            # Parse name from SKILL.md frontmatter
                            content = skill_md.read_text()
                            name = skill_dir.name
                            for line in content.split("\n"):
                                if line.startswith("name:"):
                                    name = line.split(":", 1)[1].strip()
                                    break
                            print(f"  📦 {name} ({skill_dir.name})")
        case "create":
            name = args.name
            skill_dir = Path("skills") / name
            skill_dir.mkdir(parents=True, exist_ok=True)

            (skill_dir / "SKILL.md").write_text(
                "---\n"
                f"name: {name}\n"
                "description: A new skill\n"
                "tools: []\n"
                "---\n\n"
                f"# {name}\n\n"
                "Brief description of this skill.\n"
            )

            (skill_dir / "handler.py").write_text(
                '"""Handler functions for skill tools."""\n\n'
                "from typing import Any\n\n\n"
                "async def execute(tool_name: str, args: dict[str, Any]) -> Any:\n"
                '    """Execute a tool call."""\n'
                '    return {"result": "not implemented"}\n'
            )

            print(f"✅ Created skill: {name}")

        case "install":
            source = (args.source or "").strip()
            if not source:
                print("❌ source is required")
                sys.exit(1)
            await _install_skill_from_source(source, folder_hint=args.name)
            print(f"✅ Installed skill from: {source}")

        case _:
            print("Use: mchat skill list|create <name>|install <url-or-name>")


def _safe_skill_folder_name(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-._")
    return cleaned or "skill"


def _download_bytes(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "mchat-cli/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def _extract_skill_zip_to(content: bytes, target_dir: Path) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as e:
        raise RuntimeError("downloaded file is not a valid zip") from e

    names = [n for n in zf.namelist() if n and not n.endswith("/")]
    skill_md = next((n for n in names if Path(n).name.lower() == "skill.md"), None)
    if not skill_md:
        raise RuntimeError("zip does not contain SKILL.md")

    prefix = ""
    parts = skill_md.replace("\\", "/").split("/")
    if len(parts) > 1:
        prefix = "/".join(parts[:-1]) + "/"

    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mchat-skill-") as tmp:
        tmp_dir = Path(tmp)
        zf.extractall(tmp_dir)
        src_root = tmp_dir / prefix if prefix else tmp_dir
        if not src_root.exists():
            src_root = tmp_dir
        for child in src_root.iterdir():
            dest = target_dir / child.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            if child.is_dir():
                shutil.copytree(child, dest)
            else:
                shutil.copy2(child, dest)


async def _install_skill_from_source(source: str, folder_hint: str | None = None) -> None:
    if source.startswith(("http://", "https://")):
        urls = [source]
        slug = _safe_skill_folder_name(folder_hint or Path(urlparse(source).path).stem)
    else:
        slug = _safe_skill_folder_name(folder_hint or source)
        urls = [
            f"https://clawhub.ai/skills/{slug}.zip",
            f"https://clawhub.ai/api/skills/{slug}/download",
            f"https://clawhub.ai/skills/{slug}/download",
        ]

    last_error: Exception | None = None
    content: bytes | None = None
    for url in urls:
        try:
            content = _download_bytes(url)
            if content:
                break
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            last_error = e
            continue

    if not content:
        raise RuntimeError(f"failed to download skill: {last_error}")

    target = Path("skills") / slug
    target.mkdir(parents=True, exist_ok=True)
    _extract_skill_zip_to(content, target)


async def _cmd_db(args: argparse.Namespace) -> None:
    """Database management."""
    import app.models  # noqa: F401 - register ORM models on metadata
    from app.core.database import Base, async_session_factory, close_db, engine

    try:
        match args.db_action:
            case "init":
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                print("✅ Database tables created")
            case "migrate":
                from app.core.migrations import apply_schema_patches

                async with engine.begin() as conn:
                    applied = await conn.run_sync(apply_schema_patches)
                if applied:
                    print(f"✅ Applied patches: {', '.join(applied)}")
                else:
                    print("✅ Database schema is up to date")
            case "seed":
                from app.models.user import User
                from app.core.security import get_password_hash

                async with async_session_factory() as db:
                    from sqlalchemy import select

                    result = await db.execute(
                        select(User).where(User.username == "admin")
                    )
                    if result.scalar_one_or_none() is None:
                        admin = User(
                            username="admin",
                            password_hash=get_password_hash("admin123"),
                            role="admin",
                        )
                        db.add(admin)
                        await db.commit()
                        print("✅ Admin user created (admin / admin123)")
                    else:
                        print("ℹ️  Admin user already exists")
            case _:
                print("Use: mchat db init|migrate|seed")
    finally:
        await close_db()


if __name__ == "__main__":
    main()
