"""Skill executor - execute skill tool functions in a sandboxed environment."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from loguru import logger

from app.models.skill import Skill
from app.skill.deps import warm_skill_export_deps
from app.workspace.context import get_workspace_context
from app.workspace.factory import get_workspace_provider
from app.workspace.skill_sync import ensure_skill_in_tenant


_SKIP_CONFIG_ENV_KEYS = frozenset({"secrets", "env", "prompt_body", "parameters"})


def _skill_secrets_env_dict(skill: Skill) -> dict[str, str]:
    config = skill.config or {}
    secrets = config.get("secrets") or config.get("env") or {}
    if not isinstance(secrets, dict):
        secrets = {}
    prefix = f"MCHAT_SKILL_{skill.name.upper().replace('-', '_')}_"
    env: dict[str, str] = {}
    for key, value in secrets.items():
        if value is None or str(value).strip() == "":
            continue
        env_key = str(key).strip()
        env[f"{prefix}{env_key}"] = str(value)
        env[env_key] = str(value)
    for key, value in config.items():
        if key in _SKIP_CONFIG_ENV_KEYS:
            continue
        if isinstance(value, (dict, list)):
            continue
        env[str(key)] = str(value)
        env[f"{prefix}{str(key).upper()}"] = str(value)
    return env


@contextmanager
def _skill_secrets_env(skill: Skill) -> Iterator[None]:
    """Inject skill secrets and scalar config options into process env."""
    env = _skill_secrets_env_dict(skill)
    previous: dict[str, str | None] = {}
    try:
        for key, value in env.items():
            previous[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _resolve_script_path(skill_dir: Path) -> Path | None:
    for name in ("main.py", "tool.py"):
        candidate = skill_dir / name
        if candidate.is_file():
            return candidate
    return None


def _normalize_tool_result(result: Any) -> Any:
    if result is None:
        return {"ok": True, "message": "技能执行完成（无返回内容）"}
    if isinstance(result, dict):
        return _finalize_tool_dict(result)
    if isinstance(result, (str, int, float, bool, list)):
        return result
    return str(result)


def _finalize_tool_dict(result: dict[str, Any]) -> dict[str, Any]:
    out = dict(result)
    for key in ("files", "_internal"):
        out.pop(key, None)
    assets = out.get("outbound_assets")
    if assets is not None and not isinstance(assets, list):
        out.pop("outbound_assets", None)
    return out


async def execute_skill(skill: Skill, args: dict[str, Any]) -> Any:
    """Execute a skill tool function."""
    skill_type = skill.skill_type
    try:
        if skill_type in ("tool", "function"):
            return await _execute_python_tool(skill, args)
        if skill_type == "webhook":
            return await _execute_webhook(skill, args)
        return {"error": f"Unknown skill type: {skill_type}"}
    except SystemExit as e:
        logger.error(f"Skill '{skill.name}' called sys.exit({e.code})")
        return {
            "error": (
                f"技能 '{skill.name}' 执行异常退出"
                f"{f' (code {e.code})' if e.code else ''}。"
                "请检查技能参数与 API Key 配置。"
            )
        }
    except BaseException as e:
        logger.error(f"Skill '{skill.name}' execution error: {e}")
        return {"error": str(e)}


async def _execute_python_tool(skill: Skill, args: dict[str, Any]) -> Any:
    if not skill.path:
        return {"error": "No path defined for skill"}

    ws_ctx = get_workspace_context()
    skill_dir: Path
    if ws_ctx is not None:
        try:
            skill_dir = ensure_skill_in_tenant(skill, ws_ctx)
        except FileNotFoundError as e:
            return {"error": str(e)}
    else:
        skill_dir = Path(skill.path).resolve()
        if skill_dir.is_file():
            skill_dir = skill_dir.parent

    script_path = _resolve_script_path(skill_dir)
    if script_path is None:
        return {"error": f"No script found in {skill_dir}"}

    extra_env = _skill_secrets_env_dict(skill)
    warm_skill_export_deps(skill.name, skill_dir)

    if ws_ctx is not None:
        provider = get_workspace_provider(ws_ctx)
        try:
            raw = await provider.run_python_skill(
                script_path=script_path,
                args=args,
                extra_env=extra_env,
            )
        except BaseException as e:
            logger.error(f"Python tool execution failed: {e}")
            return {"error": str(e)}
        return _normalize_tool_result(raw)

    def _run_local() -> Any:
        with _skill_secrets_env(skill):
            from app.utils.upload_paths import resolve_upload_root

            os.environ["MCHAT_UPLOAD_DIR"] = str(resolve_upload_root())
            from app.workspace.skill_runner import execute_skill_script

            return execute_skill_script(script_path, args)

    try:
        import asyncio

        raw = await asyncio.to_thread(_run_local)
        return _normalize_tool_result(raw)
    except SystemExit as e:
        logger.error(f"Python tool '{skill.name}' sys.exit({e.code})")
        return {
            "error": (
                "技能脚本异常退出，请勿在工具模式使用 argparse/sys.exit。"
                "请在技能管理中配置 API Key（secrets）。"
            )
        }
    except BaseException as e:
        logger.error(f"Python tool execution failed: {e}")
        return {"error": str(e)}


async def _execute_webhook(skill: Skill, args: dict[str, Any]) -> Any:
    import httpx

    config = skill.config or {}
    webhook_url = config.get("url", "")
    if not webhook_url:
        return {"error": "No webhook URL configured"}

    headers = {"Content-Type": "application/json"}
    config_secrets = (skill.config or {}).get("secrets") or {}
    if isinstance(config_secrets, dict):
        api_key = config_secrets.get("API_KEY") or config_secrets.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

    try:
        with _skill_secrets_env(skill):
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    webhook_url,
                    json=args,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
    except Exception as e:
        logger.error(f"Webhook skill '{skill.name}' failed: {e}")
        return {"error": str(e)}
