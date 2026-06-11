#!/usr/bin/env python3
"""Resolve a GameCenter/Cocos project directory from slug (stdlib only, no venv deps)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _load_settings(repo_root: Path) -> dict:
    env = _read_env_file(repo_root / ".env")
    env.update(_read_env_file(repo_root / "src/backend/.env"))

    candidates = [
        repo_root / "data" / "devbridge" / "admin-settings.json",
    ]
    data_root = env.get("GAMECENTER_BRIDGE_DATA_ROOT", "").strip()
    if data_root:
        candidates.insert(0, Path(data_root).expanduser().resolve().parent / "admin-settings.json")

    admin: dict = {}
    for path in candidates:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            admin = payload
            break

    gc = admin.get("gamecenter") if isinstance(admin.get("gamecenter"), dict) else {}
    source_root = (gc.get("source_root") or env.get("GAMECENTER_SOURCE_ROOT") or "").strip()
    extra_roots = [
        item.strip()
        for item in (gc.get("extra_source_roots") or [])
        if str(item).strip()
    ]
    if not extra_roots:
        env_extra = env.get("GAMECENTER_EXTRA_SOURCE_ROOTS", "").strip()
        if env_extra:
            extra_roots = [item.strip() for item in env_extra.split(",") if item.strip()]

    allowlist_raw = (gc.get("project_allowlist") or env.get("GAMECENTER_PROJECT_ALLOWLIST") or "").strip()
    allowlist = (
        {item.strip() for item in allowlist_raw.split(",") if item.strip()}
        if allowlist_raw
        else None
    )
    cocos_bin = (gc.get("cocos_creator_bin") or env.get("GAMECENTER_COCOS_CREATOR_BIN") or "").strip()
    return {
        "source_root": source_root,
        "extra_source_roots": extra_roots,
        "allowlist": allowlist,
        "cocos_creator_bin": cocos_bin,
    }


def _is_cocos_project_dir(path: Path) -> bool:
    if (path / "project.json").is_file():
        return True
    package_json = path / "package.json"
    if not package_json.is_file():
        return False
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception:
        return False
    creator = payload.get("creator")
    return isinstance(creator, dict) and bool(creator.get("version"))


def _discover_projects(settings: dict) -> list[tuple[str, Path]]:
    roots: list[Path] = []
    for item in [settings.get("source_root"), *settings.get("extra_source_roots", [])]:
        text = str(item or "").strip()
        if not text:
            continue
        root = Path(text).expanduser().resolve()
        if root.is_dir():
            roots.append(root)

    seen: set[str] = set()
    items: list[tuple[str, Path]] = []
    allowlist = settings.get("allowlist")

    for root in roots:
        try:
            entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            if entry.name in seen:
                continue
            if allowlist is not None and entry.name not in allowlist:
                continue
            if _is_cocos_project_dir(entry):
                seen.add(entry.name)
                items.append((entry.name, entry))
                continue
            try:
                children = sorted(entry.iterdir(), key=lambda p: p.name.lower())
            except OSError:
                continue
            nested = [
                child
                for child in children
                if child.is_dir() and not child.name.startswith("_") and _is_cocos_project_dir(child)
            ]
            if len(nested) == 1:
                seen.add(entry.name)
                items.append((entry.name, nested[0]))
    return items


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: resolve-gamecenter-project.py <repo_root> <slug>\n"
            "       resolve-gamecenter-project.py <repo_root> --print-cocos-bin",
            file=sys.stderr,
        )
        return 2

    repo_root = Path(sys.argv[1]).expanduser().resolve()

    if len(sys.argv) == 3 and sys.argv[2] == "--print-cocos-bin":
        settings = _load_settings(repo_root)
        print(settings.get("cocos_creator_bin") or "")
        return 0

    if len(sys.argv) != 3:
        print(
            "usage: resolve-gamecenter-project.py <repo_root> <slug>\n"
            "       resolve-gamecenter-project.py <repo_root> --print-cocos-bin",
            file=sys.stderr,
        )
        return 2

    slug = sys.argv[2].strip()
    settings = _load_settings(repo_root)
    if not settings.get("source_root") and not settings.get("extra_source_roots"):
        print("GameCenter source_root not configured", file=sys.stderr)
        return 1

    projects = _discover_projects(settings)
    for name, path in projects:
        if name == slug:
            print(path)
            return 0

    print(f"project slug not found: {slug}", file=sys.stderr)
    if projects:
        print("available slugs:", file=sys.stderr)
        for name, _ in projects:
            print(f"  - {name}", file=sys.stderr)
    else:
        print("no projects discovered under configured source_root / extra_source_roots", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
