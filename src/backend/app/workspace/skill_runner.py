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
    if skill_mod is None or api_mod is None:
        return {
            "error": (
                "技能 main() 不支持工具参数；请添加 run(**kwargs)，"
                "或提供 patent_skill.py / patent_api.py。"
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


def execute_skill_script(script_path: Path, args: dict[str, Any]) -> Any:
    """Run main.py/tool.py entry and return JSON-serializable result."""
    script_path = script_path.resolve()
    skill_dir = script_path.parent
    spec = importlib.util.spec_from_file_location("skill_entry", script_path)
    if spec is None or spec.loader is None:
        return {"error": f"Failed to load skill script: {script_path}"}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "run"):
        return module.run(**_filter_kwargs(module.run, args))
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
    if skill_mod is None or api_mod is None:
        return {"error": "技能 main() 不支持工具参数；请添加 run(**kwargs)"}
    patent_api_cls = getattr(api_mod, "PatentAPI", None)
    patent_skill_cls = getattr(skill_mod, "PatentSkill", None)
    if patent_api_cls is None or patent_skill_cls is None:
        return {"error": "专利技能缺少 PatentAPI / PatentSkill 类"}
    api = patent_api_cls()
    skill = patent_skill_cls(api)
    ns = _args_to_namespace(args)
    handler = skill.commands.get(ns.command)
    if not handler:
        return {"error": f"Unknown command: {ns.command}"}
    return handler(ns)

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
