"""Unified skill script entry for local import and container exec."""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class _SkillCLIArgs:
    """Thin namespace for CLI-based skill argument mapping."""


def _dispatch_cli(skill_dir: Path, main_module: Any, args: dict[str, Any]) -> Any:
    """Run CLI-based skills by passing args as sys.argv."""
    saved_argv = sys.argv[:]
    saved_stdout = sys.stdout
    try:
        from io import StringIO

        cli_args = [str(skill_dir / "main.py")]
        command = str(args.pop("command", None) or "fetch")
        cli_args.append(command)
        url = args.pop("url", None)
        if url:
            cli_args.append(str(url))
        for key in sorted(args.keys()):
            value = args[key]
            if value is None or value == "":
                continue
            if isinstance(value, str) and value.lower() in ("true", "false"):
                value = value.lower() == "true"
            cli_key = key
            if key == "use_proxy":
                cli_key = "proxy"
            flag = "--" + cli_key.replace("_", "-")
            if isinstance(value, bool):
                if value:
                    cli_args.append(flag)
            elif isinstance(value, (list, dict)):
                import json as _json
                cli_args.extend([flag, _json.dumps(value, ensure_ascii=False)])
            else:
                cli_args.extend([flag, str(value)])
        sys.argv = cli_args
        buf = StringIO()
        err_buf = StringIO()
        saved_stderr = sys.stderr
        sys.stdout = buf
        sys.stderr = err_buf
        try:
            main_module.main()
        except SystemExit:
            pass
        output = buf.getvalue().strip()
        err_output = err_buf.getvalue().strip()
        if output:
            try:
                return json.loads(output)
            except (json.JSONDecodeError, ValueError):
                return {"stdout": output, "stderr": err_output if err_output else None}
        if err_output:
            return {"error": err_output, "stderr": err_output}
        return {"stdout": "(no output)"}
    finally:
        sys.stdout = saved_stdout
        sys.stderr = saved_stderr
        sys.argv = saved_argv


def _filter_kwargs(func: Any, args: dict[str, Any]) -> dict[str, Any]:
    sig = inspect.signature(func)
    params = sig.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return {k: v for k, v in args.items() if v is not None}
    return {k: v for k, v in args.items() if k in params and v is not None}


def _args_to_namespace(args: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        command=str(args.get("command") or "search").lower(),
        query=args.get("query"),
        patent_id=args.get("patent_id"),
        company_name=args.get("company_name")
        or args.get("company")
        or (args.get("query") if str(args.get("command") or "").lower() == "company" else None),
        dimension=args.get("dimension"),
        page=int(args.get("page") or 1),
        page_size=int(args.get("page_size") or args.get("pageSize") or 10),
        scope=args.get("scope") or "cn",
        sort=args.get("sort"),
        details=bool(args.get("details")),
        limit=int(args.get("limit") or 20),
        type=args.get("type") or "software",
        field=args.get("field"),
        detail=bool(args.get("detail")),
        trademark_id=args.get("trademark_id") or args.get("trademark-id"),
        year_from=args.get("year_from") or None,
        year_to=args.get("year_to") or None,
    )


def _load_module(skill_dir: Path, filename: str, module_key: str) -> Any | None:
    path = skill_dir / filename
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(module_key, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dispatch_namespace(skill_dir: Path, main_module: Any, args: dict[str, Any]) -> Any:
    skill_mod = _load_module(skill_dir, "patent_skill.py", "patent_skill")
    api_mod = _load_module(skill_dir, "patent_api.py", "patent_api")
    if skill_mod is not None and api_mod is not None:
        patent_api_cls = getattr(api_mod, "PatentAPI", None)
        patent_skill_cls = getattr(skill_mod, "PatentSkill", None)
        if patent_api_cls is not None and patent_skill_cls is not None:
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
    # Fallback: run CLI-based skill by passing args as sys.argv
    return _dispatch_cli(skill_dir, main_module, args)


def execute_skill_script(script_path: Path, args: dict[str, Any]) -> Any:
    """Run main.py/tool.py entry and return JSON-serializable result.

    If the skill defines ``async def run()``, returns the coroutine for the
    caller to ``await`` (so the skill can use the platform's native async DB
    engine / async LLM provider on the main event loop, instead of needing a
    loop-blocking synchronous client on a worker thread). Synchronous skills
    are returned as-is, exactly as before.
    """
    script_path = script_path.resolve()
    skill_dir = script_path.parent
    spec = importlib.util.spec_from_file_location("skill_entry", script_path)
    if spec is None or spec.loader is None:
        return {"error": f"Failed to load skill script: {script_path}"}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "run"):
        run_fn = module.run
        if inspect.iscoroutinefunction(run_fn):
            return run_fn(**_filter_kwargs(run_fn, args))
        return run_fn(**_filter_kwargs(run_fn, args))
    if hasattr(module, "main"):
        sig = inspect.signature(module.main)
        if len(sig.parameters) == 0:
            return _dispatch_namespace(skill_dir, module, args)
        return module.main(**_filter_kwargs(module.main, args))
    return {"error": "No main() or run() function found in skill script"}


def emit_json_result(result: Any) -> None:
    if result is None:
        print(json.dumps({"ok": True, "message": "技能执行完成（无返回内容）"}))
        return
    if isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False, default=str))
        return
    if isinstance(result, (str, int, float, bool, list)):
        print(json.dumps(result, ensure_ascii=False, default=str))
        return
    print(json.dumps({"result": str(result)}, ensure_ascii=False))


RUNNER_REL_PATH = Path("data") / ".mchat" / "run_skill.py"

_RUN_SKILL_CLI = '''#!/usr/bin/env python3
"""Tenant skill runner (deployed by MChat control plane)."""
import json
import os
import sys
from pathlib import Path

# Minimal inline helpers (no app package in sidecar)
import importlib.util
import inspect
from types import SimpleNamespace

def _filter_kwargs(func, args):
    sig = inspect.signature(func)
    params = sig.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return {k: v for k, v in args.items() if v is not None}
    return {k: v for k, v in args.items() if k in params and v is not None}

def _args_to_namespace(args):
    return SimpleNamespace(
        command=str(args.get("command") or "search").lower(),
        query=args.get("query"),
        patent_id=args.get("patent_id"),
        company_name=args.get("company_name")
        or args.get("company")
        or (args.get("query") if str(args.get("command") or "").lower() == "company" else None),
        dimension=args.get("dimension"),
        page=int(args.get("page") or 1),
        page_size=int(args.get("page_size") or args.get("pageSize") or 10),
        scope=args.get("scope") or "cn",
        sort=args.get("sort"),
        details=bool(args.get("details")),
        limit=int(args.get("limit") or 20),
        type=args.get("type") or "software",
        field=args.get("field"),
        detail=bool(args.get("detail")),
        trademark_id=args.get("trademark_id") or args.get("trademark-id"),
        year_from=args.get("year_from") or None,
        year_to=args.get("year_to") or None,
    )

def _load_module(skill_dir, filename, module_key):
    path = skill_dir / filename
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(module_key, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _dispatch_namespace(skill_dir, main_module, args):
    skill_mod = _load_module(skill_dir, "patent_skill.py", "patent_skill")
    api_mod = _load_module(skill_dir, "patent_api.py", "patent_api")
    if skill_mod is not None and api_mod is not None:
        patent_api_cls = getattr(api_mod, "PatentAPI", None)
        patent_skill_cls = getattr(skill_mod, "PatentSkill", None)
        if patent_api_cls is not None and patent_skill_cls is not None:
            api = patent_api_cls()
            skill = patent_skill_cls(api)
            ns = _args_to_namespace(args)
            handler = skill.commands.get(ns.command)
            if not handler:
                return {"error": f"Unknown command: {ns.command}"}
            return handler(ns)
    return _dispatch_cli(skill_dir, main_module, dict(args))

def _dispatch_cli(skill_dir, main_module, args):
    """Run CLI-based skills by passing args as sys.argv."""
    import json as _json
    saved_argv = sys.argv[:]
    saved_stdout = sys.stdout
    try:
        from io import StringIO
        cli_args = [str(skill_dir / "main.py")]
        command = str(args.pop("command", None) or "fetch")
        cli_args.append(command)
        url = args.pop("url", None)
        if url:
            cli_args.append(str(url))
        for key in sorted(args.keys()):
            value = args[key]
            if value is None or value == "":
                continue
            if isinstance(value, str) and value.lower() in ("true", "false"):
                value = value.lower() == "true"
            flag = "--" + key.replace("_", "-")
            if isinstance(value, bool):
                if value:
                    cli_args.append(flag)
            elif isinstance(value, (list, dict)):
                cli_args.extend([flag, _json.dumps(value, ensure_ascii=False)])
            else:
                cli_args.extend([flag, str(value)])
        sys.argv = cli_args
        buf = StringIO()
        err_buf = StringIO()
        saved_stderr = sys.stderr
        sys.stdout = buf
        sys.stderr = err_buf
        try:
            main_module.main()
        except SystemExit:
            pass
        output = buf.getvalue().strip()
        err_output = err_buf.getvalue().strip()
        if output:
            try:
                return _json.loads(output)
            except (_json.JSONDecodeError, ValueError):
                return {"stdout": output, "stderr": err_output if err_output else None}
        if err_output:
            return {"error": err_output, "stderr": err_output}
        return {"stdout": "(no output)"}
    finally:
        sys.stdout = saved_stdout
        sys.stderr = saved_stderr
        sys.argv = saved_argv

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: run_skill.py <script_path>"}))
        sys.exit(1)
    script = Path(sys.argv[1]).resolve()
    args = json.loads(os.environ.get("MCHAT_SKILL_ARGS") or "{}")
    spec = importlib.util.spec_from_file_location("skill_entry", script)
    if spec is None or spec.loader is None:
        print(json.dumps({"error": f"Failed to load {script}"}))
        sys.exit(1)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "run"):
        result = module.run(**_filter_kwargs(module.run, args))
    elif hasattr(module, "main"):
        sig = inspect.signature(module.main)
        if len(sig.parameters) == 0:
            result = _dispatch_namespace(script.parent, module, args)
        else:
            result = module.main(**_filter_kwargs(module.main, args))
    else:
        result = {"error": "No main() or run() function found"}
    # Skills may declare ``async def run()`` (e.g. web-fetch); await the
    # coroutine here so async skills work inside the sidecar, not just via
    # the host-side executor that returns the coroutine to its caller.
    import asyncio as _asyncio
    if inspect.iscoroutine(result):
        result = _asyncio.run(result)
    if result is None:
        print(json.dumps({"ok": True, "message": "技能执行完成（无返回内容）"}))
    elif isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False, default=str))
    elif isinstance(result, (str, int, float, bool, list)):
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"result": str(result)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
'''


def deploy_runner_script(tenant_root: Path) -> Path:
    """Write run_skill.py into tenant data/.mchat for container exec."""
    target = tenant_root / RUNNER_REL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or target.read_text(encoding="utf-8") != _RUN_SKILL_CLI:
        target.write_text(_RUN_SKILL_CLI, encoding="utf-8")
    target.chmod(0o755)
    return target


def container_runner_path() -> str:
    return "/workspace/data/.mchat/run_skill.py"


def cli_main() -> None:
    if len(sys.argv) < 2:
        emit_json_result({"error": "usage: run_skill.py <script_path>"})
        sys.exit(1)
    script = Path(sys.argv[1])
    args = json.loads(os.environ.get("MCHAT_SKILL_ARGS") or "{}")
    try:
        emit_json_result(execute_skill_script(script, args))
    except SystemExit as exc:
        emit_json_result({"error": f"sys.exit({exc.code})"})
        sys.exit(1)
    except BaseException as exc:
        emit_json_result({"error": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
