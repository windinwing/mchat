"""Skill executor - execute skill tool functions in a sandboxed environment."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from loguru import logger

from app.core.config import settings
from app.utils.upload_paths import resolve_upload_root
from app.models.skill import Skill
from app.skill.deps import warm_skill_export_deps
from app.workspace.context import get_workspace_context
from app.workspace.factory import get_workspace_provider


_SKIP_CONFIG_ENV_KEYS = frozenset({"secrets", "env", "prompt_body", "parameters"})


@contextmanager
def _skill_secrets_env(skill: Skill) -> Iterator[None]:
    """Inject skill secrets and scalar config options into process env."""
    config = skill.config or {}
    secrets = config.get("secrets") or config.get("env") or {}
    if not isinstance(secrets, dict):
        secrets = {}

    prefix = f"MCHAT_SKILL_{skill.name.upper().replace('-', '_')}_"
    previous: dict[str, str | None] = {}
    injected: list[str] = []

    def _set_env(env_key: str, value: Any) -> None:
        if value is None or str(value).strip() == "":
            return
        env_key = str(env_key).strip()
        if env_key not in previous:
            previous[env_key] = os.environ.get(env_key)
            injected.append(env_key)
        os.environ[env_key] = str(value)

    try:
        for key, value in secrets.items():
            env_key = str(key).strip()
            _set_env(f"{prefix}{env_key}", value)
            _set_env(env_key, value)

        for key, value in config.items():
            if key in _SKIP_CONFIG_ENV_KEYS:
                continue
            if isinstance(value, (dict, list)):
                continue
            _set_env(str(key), value)
            _set_env(f"{prefix}{str(key).upper()}", value)

        yield
    finally:
        for key in injected:
            old = previous.get(key)
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


async def execute_skill(skill: Skill, args: dict[str, Any]) -> Any:
    """Execute a skill tool function.

    Supports:
    - Python script in the skill directory
    - Shell commands defined in skill config
    - Webhook calls
    """
    skill_type = skill.skill_type

    try:
        if skill_type == "tool":
            return await _execute_python_tool(skill, args)
        elif skill_type == "function":
            return await _execute_python_tool(skill, args)
        elif skill_type == "webhook":
            return await _execute_webhook(skill, args)
        else:
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


async def _execute_python_tool(
    skill: Skill, args: dict[str, Any]
) -> Any:
    """Execute a Python-based skill tool."""
    if not skill.path:
        return {"error": "No path defined for skill"}

    skill_path = Path(skill.path)
    skill_dir = skill_path.parent

    # Look for main.py or tool.py in the skill directory
    script_path = skill_dir / "main.py"
    if not script_path.exists():
        script_path = skill_dir / "tool.py"

    if not script_path.exists():
        return {"error": f"No script found in {skill_dir}"}

    def _run_blocking() -> Any:
        with _skill_secrets_env(skill):
            ws_ctx = get_workspace_context()
            if ws_ctx is not None:
                provider = get_workspace_provider(ws_ctx)
                env = provider.execution_env()
                previous_env: dict[str, str | None] = {}
                for key, value in env.items():
                    previous_env[key] = os.environ.get(key)
                    os.environ[key] = value
                upload_dir = env.get("MCHAT_UPLOAD_DIR") or str(resolve_upload_root())
            else:
                previous_env = {}
                upload_dir = str(resolve_upload_root())
                os.environ["MCHAT_UPLOAD_DIR"] = upload_dir

            try:
                warm_skill_export_deps(skill.name, skill_dir)
                spec = importlib.util.spec_from_file_location(
                    f"skill_{skill.name}", script_path
                )
                if spec is None or spec.loader is None:
                    return {"error": f"Failed to load skill module: {skill.name}"}

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "run"):
                    filtered = _filter_kwargs_for_callable(module.run, args)
                    return module.run(**filtered)

                if hasattr(module, "main"):
                    sig = inspect.signature(module.main)
                    if len(sig.parameters) == 0:
                        return _dispatch_namespace_skill(skill_dir, module, args)
                    filtered = _filter_kwargs_for_callable(module.main, args)
                    return module.main(**filtered)

                return {"error": "No main() or run() function found in skill script"}
            finally:
                for key, old in previous_env.items():
                    if old is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = old

    try:
        result = await asyncio.to_thread(_run_blocking)
        return _normalize_tool_result(result)

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


def _filter_kwargs_for_callable(func: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Pass only parameters accepted by the skill entry function."""
    sig = inspect.signature(func)
    params = sig.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return {k: v for k, v in args.items() if v is not None}
    return {
        k: v
        for k, v in args.items()
        if k in params and v is not None
    }


def _args_to_namespace(args: dict[str, Any]) -> SimpleNamespace:
    """Map tool JSON args to argparse-style namespace (patent-search CLI skills)."""
    return SimpleNamespace(
        command=str(args.get("command") or "search").lower(),
        query=args.get("query"),
        patent_id=args.get("patent_id"),
        company_name=args.get("company_name"),
        dimension=args.get("dimension"),
        page=int(args.get("page") or 1),
        page_size=int(args.get("page_size") or args.get("pageSize") or 10),
        scope=args.get("scope") or "cn",
        sort=args.get("sort") or "relation",
        details=bool(args.get("details")),
        limit=int(args.get("limit") or 20),
        type=args.get("type") or "software",
        field=args.get("field"),
        detail=bool(args.get("detail")),
        trademark_id=args.get("trademark_id") or args.get("trademark-id"),
    )


def _load_skill_module(skill_dir: Path, filename: str, module_key: str) -> Any | None:
    path = skill_dir / filename
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(module_key, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dispatch_namespace_skill(
    skill_dir: Path, main_module: Any, args: dict[str, Any]
) -> Any:
    """Execute CLI-oriented skills whose main() has no parameters (e.g. patent-search)."""
    skill_mod = _load_skill_module(
        skill_dir, "patent_skill.py", f"skill_patent_{skill_dir.name}"
    )
    api_mod = _load_skill_module(
        skill_dir, "patent_api.py", f"skill_api_{skill_dir.name}"
    )
    if skill_mod is None or api_mod is None:
        return {
            "error": (
                "技能 main() 不支持工具参数；请为技能添加 run(**kwargs)，"
                "或提供 patent_skill.py / patent_api.py 命令分发模块。"
            )
        }

    patent_api_cls = getattr(api_mod, "PatentAPI", None)
    patent_skill_cls = getattr(skill_mod, "PatentSkill", None)
    if patent_api_cls is None or patent_skill_cls is None:
        return {"error": "专利技能缺少 PatentAPI / PatentSkill 类"}

    api = patent_api_cls()
    skill = patent_skill_cls(api)

    if hasattr(main_module, "handle_analysis"):
        skill.handle_analysis = lambda a: main_module.handle_analysis(skill, a)
    if hasattr(main_module, "handle_help"):
        skill.handle_help = lambda a: main_module.handle_help(skill, a)

    ns = _args_to_namespace(args)
    handler = skill.commands.get(ns.command)
    if not handler:
        return {"error": f"Unknown command: {ns.command}"}
    return handler(ns)


def _normalize_tool_result(result: Any) -> Any:
    """Ensure tool output is JSON-serializable for the LLM."""
    if result is None:
        return {"ok": True, "message": "技能执行完成（无返回内容）"}
    if isinstance(result, dict):
        return _finalize_tool_dict(result)
    if isinstance(result, (str, int, float, bool, list)):
        return result
    return str(result)


def _finalize_tool_dict(result: dict[str, Any]) -> dict[str, Any]:
    """保留 outbound_assets；去掉仅供执行器使用的内部字段。"""
    out = dict(result)
    for key in ("files", "_internal"):
        out.pop(key, None)
    assets = out.get("outbound_assets")
    if assets is not None and not isinstance(assets, list):
        out.pop("outbound_assets", None)
    return out


async def _execute_webhook(
    skill: Skill, args: dict[str, Any]
) -> Any:
    """Execute a webhook-based skill."""
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
