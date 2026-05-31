"""技能导出可选依赖：执行工具前尝试自动安装，失败不影响其它子命令。"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from loguru import logger

_EXPORT_SKILL_NAMES = frozenset(
    {
        "patent-search",
        "patent-transaction",
        "patent-disclosure",
        "patent-report",
    }
)
_warmed = False


def _run_pip_install(package: str) -> bool:
    import shutil

    cmds: list[list[str]] = []
    uv = shutil.which("uv")
    if uv:
        cmds.append([uv, "pip", "install", package, "-q"])
    cmds.append([sys.executable, "-m", "pip", "install", package, "-q"])
    for cmd in cmds:
        try:
            proc = subprocess.run(cmd, timeout=180, capture_output=True, text=True)
            if proc.returncode == 0:
                importlib.invalidate_caches()
                return True
        except (OSError, subprocess.TimeoutExpired) as e:
            logger.debug("pip install {} failed: {}", package, e)
    return False


def ensure_backend_export_packages() -> None:
    """在 mchat 进程内为导出功能安装/加载可选依赖（幂等）。"""
    global _warmed
    if _warmed:
        return
    _warmed = True

    for package, import_name in (
        ("openpyxl", "openpyxl"),
        ("python-docx", "docx"),
        ("matplotlib", "matplotlib"),
        ("python-pptx", "pptx"),
    ):
        try:
            __import__(import_name)
            continue
        except ImportError:
            pass
        if _run_pip_install(package):
            try:
                __import__(import_name)
                logger.info("已自动安装导出依赖: {}", package)
            except ImportError:
                logger.warning("自动安装 {} 后仍无法 import {}", package, import_name)
        else:
            logger.warning(
                "导出依赖 {} 未就绪，导出将走技能内回退格式；其它工具子命令不受影响",
                package,
            )


def warm_skill_export_deps(skill_name: str, skill_dir: Path | None) -> None:
    """执行带导出能力的技能前预热可选依赖（静默）。"""
    if skill_name not in _EXPORT_SKILL_NAMES:
        return
    ensure_backend_export_packages()
    if skill_dir and skill_dir.is_dir():
        deps_file = skill_dir / "export_deps.py"
        if deps_file.is_file():
            try:
                spec = importlib.util.spec_from_file_location(
                    f"mchat_warm_{skill_name}", deps_file
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    fn = getattr(mod, "warm_export_dependencies", None)
                    if callable(fn):
                        fn()
            except Exception as e:
                logger.debug("warm {} export_deps: {}", skill_name, e)
