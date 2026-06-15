"""Generic rooted project bridge service for development providers."""

from __future__ import annotations

import base64
import fnmatch
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from fastapi import HTTPException

from app.schemas.gamecenter_bridge import (
    GamecenterFileEntry,
    GamecenterFileListResponse,
    GamecenterFileReadResponse,
    GamecenterProjectDetail,
    GamecenterProjectSummary,
)


@dataclass(slots=True)
class DiscoveredProject:
    slug: str
    path: Path
    source_root: Path


@dataclass(slots=True)
class RootedProjectBridgeConfig:
    provider_key: str
    source_root: Path
    data_root: Path
    enabled: bool
    write_enabled: bool
    project_allowlist: set[str] | None
    readable_roots: tuple[str, ...]
    root_files: set[str]
    text_extensions: set[str]
    extra_source_roots: tuple[Path, ...] = ()
    max_read_bytes: int = 256 * 1024
    max_list_entries: int = 2000
    build_command: str = ""
    build_timeout_seconds: int = 1800
    keep_builds: int = 10
    publish_enabled: bool = False
    playables_root: Path | None = None
    sync_extracted_root: Path | None = None
    playable_base_url: str = ""
    playable_base_urls: tuple[str, ...] = ()
    release_keep: int = 20
    cocos_creator_bin: str = ""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


import re

_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$")


def _safe_relpath(value: str) -> str:
    text = (value or "").strip().replace("\\", "/").strip("/")
    if not text:
        return ""
    parts = [part for part in text.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise HTTPException(status_code=400, detail="Invalid path")
    return "/".join(parts)


def _validate_slug(slug: str) -> str:
    """Strict slug validation to prevent shell injection in build commands."""
    s = (slug or "").strip()
    if not s or not _SLUG_RE.match(s):
        raise HTTPException(status_code=400, detail="Invalid project slug: use only letters, digits, dash, underscore, dot")
    return s


def _candidate_relpaths(slug: str, relpath: str, readable_roots: tuple[str, ...]) -> list[str]:
    """Normalize agent-supplied paths (strip slug prefix, try assets/ prefix)."""
    raw = _safe_relpath(relpath)
    if not raw:
        return [""]
    slug_safe = _safe_relpath(slug)
    variants: list[str] = []
    if raw not in variants:
        variants.append(raw)
    if slug_safe and raw.startswith(f"{slug_safe}/"):
        stripped = raw[len(slug_safe) + 1 :]
        if stripped and stripped not in variants:
            variants.append(stripped)
    first = raw.split("/", 1)[0]
    allowed = set(readable_roots)
    if first not in allowed:
        for root in readable_roots:
            prefixed = f"{root}/{raw}"
            if prefixed not in variants:
                variants.append(prefixed)
            if slug_safe and raw.startswith(f"{slug_safe}/"):
                stripped = raw[len(slug_safe) + 1 :]
                prefixed2 = f"{root}/{stripped}"
                if prefixed2 not in variants:
                    variants.append(prefixed2)
    return variants


class RootedProjectBridgeService:
    def __init__(self, config: RootedProjectBridgeConfig) -> None:
        self.config = config

    def _ensure_enabled(self) -> None:
        if not self.config.enabled:
            raise HTTPException(status_code=403, detail=f"{self.config.provider_key} bridge disabled")

    def _ensure_write_enabled(self) -> None:
        self._ensure_enabled()
        if not self.config.write_enabled:
            raise HTTPException(status_code=403, detail=f"{self.config.provider_key} write actions disabled")

    def _ensure_publish_enabled(self) -> None:
        self._ensure_enabled()
        if not self.config.publish_enabled or self.config.playables_root is None:
            raise HTTPException(status_code=403, detail=f"{self.config.provider_key} publish actions disabled")

    def _all_source_roots(self) -> list[Path]:
        roots = [self.config.source_root, *self.config.extra_source_roots]
        return [root for root in roots if root.is_dir()]

    @staticmethod
    def _is_cocos_project_dir(path: Path) -> bool:
        if (path / "project.json").is_file():
            return True
        package_json = path / "package.json"
        if package_json.is_file():
            try:
                payload = json.loads(package_json.read_text(encoding="utf-8"))
            except Exception:
                return False
            creator = payload.get("creator")
            return isinstance(creator, dict) and bool(creator.get("version"))
        return False

    def _discover_projects(self) -> list[DiscoveredProject]:
        self._ensure_enabled()
        seen: set[str] = set()
        items: list[DiscoveredProject] = []
        for root in self._all_source_roots():
            for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if not entry.is_dir() or entry.name.startswith("_"):
                    continue
                if entry.name in seen:
                    continue
                if self.config.project_allowlist is not None and entry.name not in self.config.project_allowlist:
                    continue
                if self._is_cocos_project_dir(entry):
                    seen.add(entry.name)
                    items.append(DiscoveredProject(slug=entry.name, path=entry, source_root=root))
                    continue
                nested = [
                    child
                    for child in sorted(entry.iterdir(), key=lambda p: p.name.lower())
                    if child.is_dir() and not child.name.startswith("_") and self._is_cocos_project_dir(child)
                ]
                if len(nested) == 1:
                    seen.add(entry.name)
                    items.append(DiscoveredProject(slug=entry.name, path=nested[0], source_root=root))
        return items

    def _discover_project_dirs(self) -> list[Path]:
        return [item.path for item in self._discover_projects()]

    def _project_state_root(self, slug: str) -> Path:
        root = self.config.data_root / slug
        (root / "changes").mkdir(parents=True, exist_ok=True)
        (root / "builds").mkdir(parents=True, exist_ok=True)
        return root

    def _project_dir(self, slug: str) -> Path:
        safe_slug = _validate_slug(slug)
        if self.config.project_allowlist is not None and safe_slug not in self.config.project_allowlist:
            raise HTTPException(status_code=403, detail="Project not allowed")
        for root in self._all_source_roots():
            outer = (root / safe_slug).resolve()
            if not outer.is_dir():
                continue
            candidates: list[Path] = []
            if self._is_cocos_project_dir(outer):
                candidates.append(outer)
            else:
                nested = [
                    child.resolve()
                    for child in sorted(outer.iterdir(), key=lambda p: p.name.lower())
                    if child.is_dir() and not child.name.startswith("_") and self._is_cocos_project_dir(child)
                ]
                if len(nested) == 1:
                    candidates.append(nested[0])
            for target in candidates:
                try:
                    target.relative_to(root.resolve())
                except ValueError:
                    continue
                return target
        raise HTTPException(status_code=404, detail="Project not found")

    def _play_urls(self, slug: str) -> list[str]:
        bases: list[str] = []
        if self.config.playable_base_urls:
            bases.extend(str(item).strip() for item in self.config.playable_base_urls if str(item).strip())
        elif self.config.playable_base_url:
            bases.append(self.config.playable_base_url.strip())
        return [f"{base.rstrip('/')}/{slug}/" for base in bases]

    @staticmethod
    def _timestamp(path: Path) -> datetime | None:
        if not path.exists():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime)

    def _build_dir(self, project_dir: Path) -> Path:
        return project_dir / "build" / "web-mobile"

    def _readable_roots(self, project_dir: Path) -> list[str]:
        return [name for name in self.config.readable_roots if (project_dir / name).exists()]

    def _top_level_files(self, project_dir: Path) -> list[str]:
        return [name for name in sorted(self.config.root_files) if (project_dir / name).is_file()]

    def list_projects(self) -> list[GamecenterProjectSummary]:
        items: list[GamecenterProjectSummary] = []
        for discovered in self._discover_projects():
            project_dir = discovered.path
            build_dir = self._build_dir(project_dir)
            items.append(
                GamecenterProjectSummary(
                    slug=discovered.slug,
                    name=discovered.slug,
                    path=str(project_dir),
                    has_build=build_dir.is_dir(),
                    source_updated_at=self._timestamp(project_dir),
                    build_updated_at=self._timestamp(build_dir),
                    preview_path="build/web-mobile" if build_dir.is_dir() else None,
                )
            )
        return items

    def get_project(self, slug: str) -> GamecenterProjectDetail:
        project_dir = self._project_dir(slug)
        build_dir = self._build_dir(project_dir)
        return GamecenterProjectDetail(
            slug=slug,
            name=slug,
            path=str(project_dir),
            has_build=build_dir.is_dir(),
            source_updated_at=self._timestamp(project_dir),
            build_updated_at=self._timestamp(build_dir),
            preview_path="build/web-mobile" if build_dir.is_dir() else None,
            readable_roots=self._readable_roots(project_dir),
            top_level_files=self._top_level_files(project_dir),
        )

    def _resolve_browsable_path(self, project_dir: Path, relpath: str) -> Path:
        rel = _safe_relpath(relpath)
        if not rel:
            return project_dir
        first = rel.split("/", 1)[0]
        if first not in self.config.readable_roots and first not in self.config.root_files:
            raise HTTPException(status_code=403, detail="Path not allowed")
        target = (project_dir / rel).resolve()
        try:
            target.relative_to(project_dir)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Path outside project root") from exc
        return target

    def _resolve_writable_path(
        self,
        project_dir: Path,
        relpath: str,
        *,
        slug: str = "",
        create_if_missing: bool = False,
    ) -> Path:
        last_detail = "Writable file not found"
        for candidate in _candidate_relpaths(slug, relpath, self.config.readable_roots):
            try:
                target = self._resolve_browsable_path(project_dir, candidate)
            except HTTPException as exc:
                last_detail = str(exc.detail)
                continue
            if target.is_file():
                if target.suffix.lower() not in self.config.text_extensions:
                    raise HTTPException(status_code=400, detail="Only text-like files are writable")
                return target
            if create_if_missing and target.suffix.lower() in self.config.text_extensions:
                parent = target.parent
                if parent.is_dir() or parent == project_dir:
                    parent.mkdir(parents=True, exist_ok=True)
                    return target
        roots = ", ".join(self.config.readable_roots)
        raise HTTPException(
            status_code=404,
            detail=(
                f"{last_detail}: `{relpath}` under project `{project_dir}` "
                f"(use relative paths like assets/scripts/foo.ts; allowed roots: {roots})"
            ),
        )

    def list_files(self, slug: str, relpath: str = "") -> GamecenterFileListResponse:
        project_dir = self._project_dir(slug)
        target = self._resolve_browsable_path(project_dir, relpath)
        if target.is_file():
            return GamecenterFileListResponse(
                project=slug,
                path=_safe_relpath(relpath),
                items=[
                    GamecenterFileEntry(
                        path=_safe_relpath(relpath),
                        name=target.name,
                        is_dir=False,
                        size=target.stat().st_size,
                        updated_at=self._timestamp(target),
                    )
                ],
            )
        if not target.exists() or not target.is_dir():
            raise HTTPException(status_code=404, detail="Path not found")

        items: list[GamecenterFileEntry] = []
        if target == project_dir:
            for name in self._readable_roots(project_dir):
                path = project_dir / name
                items.append(GamecenterFileEntry(path=name, name=name, is_dir=True, size=0, updated_at=self._timestamp(path)))
            for name in self._top_level_files(project_dir):
                path = project_dir / name
                items.append(GamecenterFileEntry(path=name, name=name, is_dir=False, size=path.stat().st_size, updated_at=self._timestamp(path)))
            return GamecenterFileListResponse(project=slug, path="", items=items)

        for index, child in enumerate(sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))):
            if index >= self.config.max_list_entries:
                break
            if child.name.startswith("."):
                continue
            rel_child = child.relative_to(project_dir).as_posix()
            if child.is_file() and child.suffix.lower() not in self.config.text_extensions:
                continue
            items.append(
                GamecenterFileEntry(
                    path=rel_child,
                    name=child.name,
                    is_dir=child.is_dir(),
                    size=0 if child.is_dir() else child.stat().st_size,
                    updated_at=self._timestamp(child),
                )
            )
        return GamecenterFileListResponse(project=slug, path=target.relative_to(project_dir).as_posix(), items=items)

    def read_file(self, slug: str, relpath: str) -> GamecenterFileReadResponse:
        project_dir = self._project_dir(slug)
        target: Path | None = None
        for candidate in _candidate_relpaths(slug, relpath, self.config.readable_roots):
            try:
                maybe = self._resolve_browsable_path(project_dir, candidate)
            except HTTPException:
                continue
            if maybe.is_file():
                target = maybe
                break
        if target is None:
            raise HTTPException(status_code=404, detail=f"File not found: {relpath}")
        if target.suffix.lower() not in self.config.text_extensions:
            raise HTTPException(status_code=400, detail="Only text-like files are supported")
        size = target.stat().st_size
        if size > self.config.max_read_bytes:
            raise HTTPException(status_code=413, detail="File too large for preview")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="File is not UTF-8 text") from exc
        return GamecenterFileReadResponse(
            project=slug,
            path=target.relative_to(project_dir).as_posix(),
            content=content,
            size=size,
            updated_at=self._timestamp(target),
        )

    def patch_file(self, slug: str, relpath: str, *, content: str, actor_user_id: str, summary: str | None = None) -> dict:
        self._ensure_write_enabled()
        project_dir = self._project_dir(slug)
        target = self._resolve_writable_path(
            project_dir,
            relpath,
            slug=slug,
            create_if_missing=True,
        )
        is_new = not target.exists()
        before_text = target.read_text(encoding="utf-8") if target.is_file() else ""
        if before_text == content:
            rel = target.relative_to(project_dir).as_posix()
            return {
                "ok": True,
                "unchanged": True,
                "provider": self.config.provider_key,
                "project": slug,
                "path": rel,
                "created": is_new,
            }
        change_id = uuid.uuid4().hex
        change_root = self._project_state_root(slug) / "changes" / change_id
        change_root.mkdir(parents=True, exist_ok=True)
        (change_root / "before.txt").write_text(before_text, encoding="utf-8")
        (change_root / "after.txt").write_text(content, encoding="utf-8")
        metadata = {
            "id": change_id,
            "provider": self.config.provider_key,
            "project": slug,
            "path": target.relative_to(project_dir).as_posix(),
            "summary": (summary or "").strip() or None,
            "status": "applied",
            "actor_user_id": actor_user_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "reverted_at": None,
            "before_sha256": _sha256_text(before_text),
            "after_sha256": _sha256_text(content),
            "before_size": len(before_text.encode("utf-8")),
            "after_size": len(content.encode("utf-8")),
        }
        (change_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        target.write_text(content, encoding="utf-8")
        return {"ok": True, **metadata}

    def list_changes(self, slug: str) -> list[dict]:
        self._project_dir(slug)
        changes_root = self._project_state_root(slug) / "changes"
        items: list[dict] = []
        for entry in sorted(changes_root.iterdir(), key=lambda p: p.name, reverse=True):
            meta_path = entry / "metadata.json"
            if not meta_path.is_file():
                continue
            try:
                items.append(json.loads(meta_path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return items

    def revert_change(self, slug: str, change_id: str, *, actor_user_id: str) -> dict:
        self._ensure_write_enabled()
        project_dir = self._project_dir(slug)
        change_root = self._project_state_root(slug) / "changes" / change_id
        meta_path = change_root / "metadata.json"
        before_path = change_root / "before.txt"
        if not meta_path.is_file() or not before_path.is_file():
            raise HTTPException(status_code=404, detail="Change record not found")
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        target = self._resolve_writable_path(project_dir, metadata["path"], slug=slug)
        target.write_text(before_path.read_text(encoding="utf-8"), encoding="utf-8")
        metadata["status"] = "reverted"
        metadata["reverted_at"] = datetime.now().isoformat(timespec="seconds")
        metadata["reverted_by"] = actor_user_id
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, **metadata}

    # ── git integration ──

    _GITIGNORE_CONTENT = "library/\ntemp/\nbuild/\nnode_modules/\n.idea/\n.vscode/\n*.log\n"

    @staticmethod
    def _git(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(project_dir), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def git_init(self, slug: str) -> dict:
        self._ensure_write_enabled()
        project_dir = self._project_dir(slug)
        if (project_dir / ".git").is_dir():
            raise HTTPException(status_code=409, detail="Git already initialized")
        proc = self._git(project_dir, "init")
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"git init failed: {proc.stderr.strip()}")
        gitignore = project_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(self._GITIGNORE_CONTENT)
        self._git(project_dir, "add", "-A")
        self._git(project_dir, "commit", "-m", "Initial commit (DevBridge)")
        return {"ok": True, "slug": slug, "action": "initialized"}

    def git_commit(self, slug: str, message: str) -> dict:
        self._ensure_write_enabled()
        project_dir = self._project_dir(slug)
        if not (project_dir / ".git").is_dir():
            raise HTTPException(status_code=400, detail="Git not initialized. Use git_init first.")
        msg = (message or "Update via DevBridge").strip()[:500]
        self._git(project_dir, "add", "-A")
        proc = self._git(project_dir, "commit", "-m", msg)
        if proc.returncode != 0:
            detail = proc.stdout.strip() + "\n" + proc.stderr.strip()
            if "nothing to commit" in detail.lower():
                return {"ok": True, "slug": slug, "message": msg, "status": "nothing_to_commit"}
            raise HTTPException(status_code=500, detail=f"git commit failed: {detail}")
        log = self._git(project_dir, "log", "-1", "--oneline")
        return {"ok": True, "slug": slug, "message": msg, "commit": log.stdout.strip()}

    def git_status(self, slug: str) -> dict:
        self._ensure_enabled()
        project_dir = self._project_dir(slug)
        if not (project_dir / ".git").is_dir():
            return {"ok": True, "slug": slug, "initialized": False, "files": []}
        proc = self._git(project_dir, "status", "--porcelain")
        lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
        files = [{"status": l[:2].strip(), "file": l[3:]} for l in lines]
        has_remote = self._git(project_dir, "remote", "get-url", "origin").returncode == 0
        return {"ok": True, "slug": slug, "initialized": True, "has_remote": has_remote, "files": files}

    def git_log(self, slug: str, *, max_count: int = 20) -> dict:
        self._ensure_enabled()
        project_dir = self._project_dir(slug)
        if not (project_dir / ".git").is_dir():
            return {"ok": True, "slug": slug, "initialized": False, "commits": []}
        proc = self._git(project_dir, "log", f"-{min(max_count, 100)}", "--oneline", "--decorate")
        commits = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
        return {"ok": True, "slug": slug, "initialized": True, "commits": commits}

    def git_set_remote(self, slug: str, remote_url: str) -> dict:
        self._ensure_write_enabled()
        project_dir = self._project_dir(slug)
        if not (project_dir / ".git").is_dir():
            raise HTTPException(status_code=400, detail="Git not initialized. Use git_init first.")
        url = remote_url.strip()
        if not url:
            raise HTTPException(status_code=400, detail="Remote URL is required")
        self._git(project_dir, "remote", "remove", "origin")
        proc = self._git(project_dir, "remote", "add", "origin", url)
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"git remote add failed: {proc.stderr.strip()}")
        return {"ok": True, "slug": slug, "remote_url": url}

    def git_push(self, slug: str) -> dict:
        self._ensure_write_enabled()
        project_dir = self._project_dir(slug)
        if not (project_dir / ".git").is_dir():
            raise HTTPException(status_code=400, detail="Git not initialized. Use git_init first.")
        proc = self._git(project_dir, "push", "-u", "origin", "HEAD")
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"git push failed: {proc.stderr.strip()}")
        return {"ok": True, "slug": slug, "pushed": True}

    def _write_build_metadata(self, build_root: Path, metadata: dict) -> None:
        build_root.mkdir(parents=True, exist_ok=True)
        (build_root / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _run_build_subprocess(
        self,
        slug: str,
        *,
        build_id: str,
        build_root: Path,
        project_dir: Path,
        rendered: str,
        metadata: dict,
    ) -> dict:
        env = os.environ.copy()
        env["GAMECENTER_BUILD_ID"] = build_id
        if self.config.cocos_creator_bin:
            env["GAMECENTER_COCOS_CREATOR_BIN"] = self.config.cocos_creator_bin
        result = subprocess.run(
            ["/bin/bash", "-lc", rendered],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=self.config.build_timeout_seconds,
            env=env,
        )
        (build_root / "stdout.log").write_text(result.stdout or "", encoding="utf-8")
        (build_root / "stderr.log").write_text(result.stderr or "", encoding="utf-8")
        build_dir = self._build_dir(project_dir)
        snapshot_dir: str | None = None
        status_text = "failed"
        if result.returncode == 0 and build_dir.is_dir():
            snapshot_path = project_dir / "build" / ".mchat-release" / build_id
            if snapshot_path.exists():
                shutil.rmtree(snapshot_path)
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(build_dir, snapshot_path)
            snapshot_dir = str(snapshot_path)
            status_text = "built"
            keep = max(int(self.config.keep_builds or 10), 1)
            siblings = sorted(snapshot_path.parent.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in siblings[keep:]:
                if old.is_dir():
                    shutil.rmtree(old, ignore_errors=True)
        metadata.update(
            {
                "status": status_text,
                "build_output_dir": str(build_dir) if build_dir.is_dir() else None,
                "snapshot_dir": snapshot_dir,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "returncode": result.returncode,
            }
        )
        self._write_build_metadata(build_root, metadata)
        if result.returncode != 0:
            detail = f"Build failed with exit code {result.returncode}"
            stderr_tail = (result.stderr or "").strip()[-1500:]
            if stderr_tail:
                detail = f"{detail}\n{stderr_tail}"
            raise HTTPException(status_code=400, detail=detail)
        stdout_tail = (result.stdout or "").strip()[-2500:]
        return {"ok": True, "stdout_tail": stdout_tail or None, **metadata}

    def build_project(self, slug: str, *, actor_user_id: str, summary: str | None = None) -> dict:
        self._ensure_write_enabled()
        project_dir = self._project_dir(slug)
        command = (self.config.build_command or "").strip()
        if not command:
            raise HTTPException(status_code=503, detail=f"{self.config.provider_key} build command not configured")
        build_id = uuid.uuid4().hex
        build_root = self._project_state_root(slug) / "builds" / build_id
        rendered = command.replace("{project_dir}", str(project_dir)).replace("{slug}", slug).replace("{build_id}", build_id)
        metadata = {
            "id": build_id,
            "provider": self.config.provider_key,
            "project": slug,
            "status": "queued",
            "command": rendered,
            "build_output_dir": None,
            "snapshot_dir": None,
            "summary": (summary or "").strip() or None,
            "actor_user_id": actor_user_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._write_build_metadata(build_root, metadata)

        from app.services.build_queue_service import enqueue_build_job, queue_enabled

        if queue_enabled():
            enqueue_build_job(
                {
                    "provider_key": self.config.provider_key,
                    "slug": slug,
                    "build_id": build_id,
                    "build_root": str(build_root),
                    "project_dir": str(project_dir),
                    "command": rendered,
                    "timeout_seconds": self.config.build_timeout_seconds,
                    "cocos_creator_bin": self.config.cocos_creator_bin or "",
                    "keep_builds": self.config.keep_builds,
                }
            )
            return {"ok": True, "queued": True, "stdout_tail": None, **metadata}

        metadata["status"] = "running"
        metadata["started_at"] = datetime.now().isoformat(timespec="seconds")
        self._write_build_metadata(build_root, metadata)
        return self._run_build_subprocess(
            slug,
            build_id=build_id,
            build_root=build_root,
            project_dir=project_dir,
            rendered=rendered,
            metadata=metadata,
        )

    def run_queued_build(self, job: dict) -> dict:
        """Worker entry: run subprocess for a queued job."""
        build_root = Path(str(job.get("build_root") or ""))
        meta_path = build_root / "metadata.json"
        if not meta_path.is_file():
            raise HTTPException(status_code=404, detail="Build metadata not found")
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        metadata["status"] = "running"
        metadata["started_at"] = datetime.now().isoformat(timespec="seconds")
        self._write_build_metadata(build_root, metadata)
        slug = str(job.get("slug") or metadata.get("project") or "")
        project_dir = Path(str(job.get("project_dir") or ""))
        build_id = str(job.get("build_id") or metadata.get("id") or "")
        rendered = str(job.get("command") or metadata.get("command") or "")
        try:
            return self._run_build_subprocess(
                slug,
                build_id=build_id,
                build_root=build_root,
                project_dir=project_dir,
                rendered=rendered,
                metadata=metadata,
            )
        except HTTPException:
            raise
        except Exception as exc:
            metadata["status"] = "failed"
            metadata["finished_at"] = datetime.now().isoformat(timespec="seconds")
            metadata["error"] = str(exc)
            self._write_build_metadata(build_root, metadata)
            raise

    def list_builds(self, slug: str) -> list[dict]:
        self._project_dir(slug)
        builds_root = self._project_state_root(slug) / "builds"
        items: list[dict] = []
        for entry in sorted(builds_root.iterdir(), key=lambda p: p.name, reverse=True):
            meta_path = entry / "metadata.json"
            if not meta_path.is_file():
                continue
            try:
                items.append(json.loads(meta_path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return items

    def _playable_project_root(self, slug: str) -> Path:
        assert self.config.playables_root is not None
        root = self.config.playables_root / slug
        (root / "releases").mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _validate_release_dir(release_dir: Path) -> None:
        if not release_dir.is_dir():
            raise HTTPException(status_code=404, detail="Release directory not found")
        candidates = list(release_dir.glob("index.html")) + list(release_dir.glob("**/*.html"))
        if not candidates:
            raise HTTPException(status_code=400, detail="Release artifact missing HTML entry")

    def _sync_extracted_release(self, slug: str, release_dir: Path) -> str | None:
        if self.config.sync_extracted_root is None:
            return None
        target = self.config.sync_extracted_root / slug
        if target.exists() or target.is_symlink():
            if target.is_symlink() or target.is_file():
                target.unlink()
            else:
                shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(release_dir, target)
        return str(target)

    def _switch_current_release(self, slug: str, release_id: str) -> Path:
        project_root = self._playable_project_root(slug)
        release_dir = project_root / "releases" / release_id
        self._validate_release_dir(release_dir)
        current_link = project_root / "current"
        if current_link.is_symlink() or current_link.exists():
            current_link.unlink()
        current_link.symlink_to(Path("releases") / release_id)
        return release_dir

    def publish_build(self, slug: str, build_id: str, *, actor_user_id: str, summary: str | None = None) -> dict:
        self._ensure_publish_enabled()
        self._project_dir(slug)
        build_root = self._project_state_root(slug) / "builds" / build_id
        meta_path = build_root / "metadata.json"
        if not meta_path.is_file():
            raise HTTPException(status_code=404, detail="Build record not found")
        build_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        snapshot_dir = build_meta.get("snapshot_dir")
        if not snapshot_dir or not Path(snapshot_dir).is_dir():
            raise HTTPException(status_code=400, detail="Build snapshot not available for publish")
        release_id = build_id
        release_dir = self._playable_project_root(slug) / "releases" / release_id
        if release_dir.exists():
            shutil.rmtree(release_dir, ignore_errors=True)
        shutil.copytree(snapshot_dir, release_dir)
        self._validate_release_dir(release_dir)
        previous = None
        current_link = self._playable_project_root(slug) / "current"
        if current_link.is_symlink():
            previous = Path(os.readlink(current_link)).name
        self._switch_current_release(slug, release_id)
        synced_extracted = self._sync_extracted_release(slug, release_dir)
        keep = max(int(self.config.release_keep or 20), 1)
        releases_root = self._playable_project_root(slug) / "releases"
        # Identify the release currently pointed to by 'current' symlink
        current_link = self._playable_project_root(slug) / "current"
        current_target = current_link.resolve().name if current_link.is_symlink() else None
        siblings = sorted(releases_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in siblings[keep:]:
            if old.is_dir() and old.name != current_target:
                shutil.rmtree(old, ignore_errors=True)
        play_urls = self._play_urls(slug)
        play_url = play_urls[0] if play_urls else None
        metadata = {
            "id": release_id,
            "provider": self.config.provider_key,
            "project": slug,
            "build_id": build_id,
            "status": "published",
            "summary": (summary or "").strip() or None,
            "actor_user_id": actor_user_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "previous_release_id": previous,
            "release_dir": str(release_dir),
            "synced_extracted_dir": synced_extracted,
            "play_url": play_url,
            "play_urls": play_urls,
        }
        release_meta_path = release_dir / ".mchat-release.json"
        release_meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, **metadata}

    def list_releases(self, slug: str) -> list[dict]:
        self._ensure_publish_enabled()
        self._project_dir(slug)
        project_root = self._playable_project_root(slug)
        current_id = None
        current_link = project_root / "current"
        if current_link.is_symlink():
            current_id = Path(os.readlink(current_link)).name
        items: list[dict] = []
        releases_root = project_root / "releases"
        for entry in sorted(releases_root.iterdir(), key=lambda p: p.name, reverse=True):
            if not entry.is_dir():
                continue
            meta_path = entry / ".mchat-release.json"
            payload = {
                "id": entry.name,
                "project": slug,
                "is_current": entry.name == current_id,
                "release_dir": str(entry),
            }
            if meta_path.is_file():
                try:
                    payload.update(json.loads(meta_path.read_text(encoding="utf-8")))
                except Exception:
                    pass
            items.append(payload)
        return items

    def rollback_release(self, slug: str, release_id: str, *, actor_user_id: str) -> dict:
        self._ensure_publish_enabled()
        self._project_dir(slug)
        release_dir = self._switch_current_release(slug, release_id)
        synced_extracted = self._sync_extracted_release(slug, release_dir)
        play_urls = self._play_urls(slug)
        play_url = play_urls[0] if play_urls else None
        return {
            "ok": True,
            "provider": self.config.provider_key,
            "project": slug,
            "release_id": release_id,
            "status": "rolled_back",
            "actor_user_id": actor_user_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "synced_extracted_dir": synced_extracted,
            "play_url": play_url,
            "play_urls": play_urls,
        }

    # ── search ──

    def search_files(self, slug: str, pattern: str, *, path_hint: str = "", max_matches: int = 40) -> dict:
        self._ensure_enabled()
        project_dir = self._project_dir(slug)
        # Always use re.escape to prevent ReDoS; users search by literal text.
        # If regex is needed, it should be an explicit opt-in feature.
        compiled = re.compile(re.escape(pattern), re.IGNORECASE)
        hint_path = _safe_relpath(path_hint)
        walk_root = project_dir
        if hint_path:
            hint_full = project_dir / hint_path
            if hint_full.is_dir():
                walk_root = hint_full
            elif hint_full.parent.is_dir():
                walk_root = hint_full.parent

        results: list[dict] = []
        scanned = 0
        for dirpath, _, filenames in os.walk(walk_root):
            rel_dir = Path(dirpath).relative_to(project_dir)
            if any(part.startswith(".") or part in {"node_modules", "library", "temp", "build", ".git"} for part in rel_dir.parts):
                continue
            restricted = False
            if self.config.readable_roots:
                dir_str = str(rel_dir).replace("\\", "/").strip(".")
                if dir_str and not any(dir_str == r.strip("/") or dir_str.startswith(r.strip("/") + "/") for r in self.config.readable_roots):
                    restricted = True
            if restricted and str(rel_dir) != ".":
                continue
            for fname in sorted(filenames):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in self.config.text_extensions and (str(rel_dir) != "." or fname not in self.config.root_files):
                    continue
                fpath = Path(dirpath) / fname
                try:
                    if fpath.stat().st_size > self.config.max_read_bytes:
                        continue
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                scanned += 1
                for li, line in enumerate(text.splitlines(), start=1):
                    if compiled.search(line):
                        snippet = line[:200]
                        results.append({
                            "file": str(Path(rel_dir) / fname).replace("\\", "/"),
                            "line": li,
                            "text": snippet.strip(),
                        })
                        if len(results) >= max_matches:
                            break
                if len(results) >= max_matches:
                    break
            if len(results) >= max_matches:
                break
        return {
            "slug": slug,
            "pattern": pattern,
            "matches": len(results),
            "scanned_files": scanned,
            "results": results,
            "truncated": len(results) >= max_matches,
        }

    # ── diff ──

    def diff_change(self, slug: str, change_id: str) -> dict:
        self._ensure_enabled()
        self._project_dir(slug)
        state_root = self._project_state_root(slug)
        change_dir = state_root / "changes" / change_id
        if not change_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"Change not found: {change_id}")
        meta_path = change_dir / "metadata.json"
        before_path = change_dir / "before.txt"
        after_path = change_dir / "after.txt"
        result: dict = {"id": change_id, "slug": slug}
        if meta_path.is_file():
            try:
                result["metadata"] = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                result["metadata"] = {}
        if before_path.is_file():
            result["before"] = before_path.read_text(encoding="utf-8")
        if after_path.is_file():
            result["after"] = after_path.read_text(encoding="utf-8")
        if "before" in result and "after" in result:
            before_lines = result["before"].splitlines()
            after_lines = result["after"].splitlines()
            diff_lines: list[str] = []
            max_len = max(len(before_lines), len(after_lines))
            changed = 0
            for i in range(max_len):
                bl = before_lines[i] if i < len(before_lines) else ""
                al = after_lines[i] if i < len(after_lines) else ""
                if bl != al:
                    changed += 1
                    if bl:
                        diff_lines.append(f"- {bl}")
                    if al:
                        diff_lines.append(f"+ {al}")
                elif changed < 20:
                    if len(diff_lines) > 0:
                        diff_lines.append(f"  {bl}")
            result["diff"] = "\n".join(diff_lines[:80])
            result["lines_changed"] = changed
        return result

    # ── create project ──

    _TEMPLATES: dict[str, dict] = {
        "cocos-simple-game": {
            "files": {
                "package.json": '{"name":"game","version":"1.0.0","creator":{"version":"3.8.8"},"description":"Cocos Creator game"}\n',
                "project.json": '{"engine":"cocos2d-js","version":"3.8.8","modules":["2d","ui","animation","audio"],"hasPreloadScript":true,"useWebGPU":false}\n',
                "tsconfig.json": '{"compilerOptions":{"target":"ES2015","module":"ES2015","strict":true,"types":["cc"]},"include":["assets/**/*.ts"]}\n',
                "assets/scripts/Game.ts": 'import { _decorator, Component, Node, director } from \'cc\';\nconst { ccclass, property } = _decorator;\n\n@ccclass(\'Game\')\nexport class Game extends Component {\n  @property(Node) uiRoot: Node | null = null;\n\n  onLoad() {\n    console.log(\'Game started\');\n  }\n\n  start() {\n    // TODO: init game logic\n  }\n\n  update(dt: number) {\n    // TODO: game loop\n  }\n}\n',
                "assets/scripts/UIController.ts": 'import { _decorator, Component, Label } from \'cc\';\nconst { ccclass, property } = _decorator;\n\n@ccclass(\'UIController\')\nexport class UIController extends Component {\n  @property(Label) scoreLabel: Label | null = null;\n  @property(Label) titleLabel: Label | null = null;\n\n  onLoad() {\n    if (this.titleLabel) this.titleLabel.string = \'My Game\';\n    if (this.scoreLabel) this.scoreLabel.string = \'Score: 0\';\n  }\n\n  setScore(score: number) {\n    if (this.scoreLabel) this.scoreLabel.string = `Score: ${score}`;\n  }\n}\n',
            },
            "description": "Cocos Creator simple game with Canvas, Game.ts, UIController.ts",
        },
        "cocos-empty": {
            "files": {
                "package.json": '{"name":"game","version":"1.0.0","creator":{"version":"3.8.8"}}\n',
                "project.json": '{"engine":"cocos2d-js","version":"3.8.8","modules":["2d","ui"],"useWebGPU":false}\n',
                "tsconfig.json": '{"compilerOptions":{"target":"ES2015","module":"ES2015","strict":true,"types":["cc"]},"include":["assets/**/*.ts"]}\n',
            },
            "description": "Minimal Cocos Creator project with no scripts or scenes",
        },
        "web-frontend": {
            "files": {
                "index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>My App</title>\n  <link rel="stylesheet" href="style.css">\n</head>\n<body>\n  <div id="app"></div>\n  <script src="main.js"></script>\n</body>\n</html>\n',
                "style.css": "*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }\nbody { font-family: system-ui, sans-serif; min-height: 100vh; }\n",
                "main.js": "'use strict';\n\ndocument.addEventListener(\'DOMContentLoaded\', () => {\n  console.log(\'App ready\');\n});\n",
            },
            "description": "Basic HTML/CSS/JS frontend project",
        },
        "node-backend": {
            "files": {
                "package.json": '{"name":"my-backend","version":"1.0.0","private":true,"scripts":{"dev":"ts-node src/index.ts","build":"tsc"},"dependencies":{},"devDependencies":{"typescript":"^5.0","ts-node":"^10.0","@types/node":"^20.0"}}\n',
                "tsconfig.json": '{"compilerOptions":{"target":"ES2020","module":"commonjs","strict":true,"esModuleInterop":true,"outDir":"dist","rootDir":"src"},"include":["src/**/*.ts"]}\n',
                "src/index.ts": 'import http from \'http\';\n\nconst PORT = process.env.PORT || 3000;\n\nconst server = http.createServer((_req, res) => {\n  res.writeHead(200, { \'Content-Type\': \'application/json\' });\n  res.end(JSON.stringify({ ok: true }));\n});\n\nserver.listen(PORT, () => console.log(`Listening on :${PORT}`));\n',
            },
            "description": "Node.js TypeScript backend scaffold",
        },
    }

    def create_project(self, slug: str, template: str, *, provider_key: str | None = None) -> dict:
        slug_safe = _validate_slug(slug)
        actual_provider = provider_key or self.config.provider_key
        source_root = self.config.source_root
        project_dir = source_root / slug_safe
        if project_dir.exists():
            raise HTTPException(status_code=409, detail=f"Project already exists: {slug_safe}")

        tmpl_def = self._TEMPLATES.get(template)
        if tmpl_def is None:
            names = ", ".join(sorted(self._TEMPLATES.keys()))
            raise HTTPException(status_code=400, detail=f"Unknown template '{template}'. Available: {names}")

        created: list[str] = []
        for rel, content in sorted(tmpl_def.get("files", {}).items()):
            target = project_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if content is not None:
                target.write_text(content, encoding="utf-8")
            else:
                target.touch()
            created.append(rel)

        if template == "cocos-simple-game":
            scene_path = project_dir / "assets" / "scenes" / "start.scene"
            scene_path.parent.mkdir(parents=True, exist_ok=True)
            scene_path.write_text(
                json.dumps(
                    [
                        {"__type__": "cc.SceneAsset", "_name": "start", "_objFlags": 0, "_native": "", "scene": {"__id__": 1}},
                        {"__type__": "cc.Scene", "_name": "start", "_objFlags": 0, "_children": [], "_active": True, "autoReleaseAssets": False, "_globals": {"__id__": 2}},
                        {"__type__": "cc.Node", "_name": "Canvas", "_objFlags": 0, "_parent": {"__id__": 1}, "_children": [], "_active": True, "_components": [{"__id__": 3}, {"__id__": 4}], "_prefab": None, "_lpos": {"__type__": "cc.Vec3", "x": 640, "y": 360, "z": 0}, "_lrot": {"__type__": "cc.Quat", "x": 0, "y": 0, "z": 0, "w": 1}, "_lscale": {"__type__": "cc.Vec3", "x": 1, "y": 1, "z": 1}},
                        {"__type__": "cc.Canvas", "_name": "", "_objFlags": 0, "node": {"__id__": 2}, "_enabled": True, "__prefab": None, "cameraComponent": {"__id__": 5}, "alignCanvasWithScreen": True},
                        {"__type__": "cc.UITransform", "_name": "", "_objFlags": 0, "node": {"__id__": 2}, "_enabled": True, "__prefab": None, "contentSize": {"__type__": "cc.Size", "width": 1280, "height": 720}, "anchorPoint": {"__type__": "cc.Vec2", "x": 0.5, "y": 0.5}},
                        {"__type__": "cc.Camera", "_name": "Camera", "_objFlags": 0, "node": {"__id__": 2}, "_enabled": True, "__prefab": None, "projection": 0, "clearFlags": 7, "backgroundColor": {"__type__": "cc.Color", "r": 0, "g": 0, "b": 0, "a": 255}, "depth": -1, "zoomRatio": 1, "visibility": -1},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        self._auto_allowlist_slug(slug_safe, actual_provider)

        return {
            "ok": True,
            "provider": actual_provider,
            "slug": slug_safe,
            "template": template,
            "template_description": tmpl_def.get("description", ""),
            "project_dir": str(project_dir),
            "created_files": created,
        }

    @staticmethod
    def _auto_allowlist_slug(slug: str, provider_key: str) -> bool:
        """Add slug to the provider's global project allowlist in admin settings.
        Only appends if a non-empty allowlist already exists (i.e. whitelist mode is active).
        If the allowlist is empty/none, all projects are allowed so no change is needed."""
        try:
            from app.services.devbridge_admin_settings import (
                load_devbridge_admin_settings,
                save_devbridge_admin_settings,
            )
        except Exception:
            return False
        try:
            settings_obj = load_devbridge_admin_settings()
            if provider_key == "gamecenter":
                gc = settings_obj.gamecenter
                current = (gc.project_allowlist or "").strip()
                if not current:
                    return False  # allowlist is empty → all projects allowed, no change needed
                slugs = [s.strip() for s in current.split(",") if s.strip()]
                if slug not in slugs:
                    slugs.append(slug)
                    gc.project_allowlist = ",".join(slugs)
                    save_devbridge_admin_settings(settings_obj)
                return True
            return False
        except Exception:
            return False

    # ── upload asset ──

    _ASSET_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}
    _ASSET_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".aac"}
    _ASSET_MODEL_EXTS = {".fbx", ".gltf", ".glb", ".obj"}
    _ASSET_ALLOWED_EXTS = _ASSET_IMAGE_EXTS | _ASSET_AUDIO_EXTS | _ASSET_MODEL_EXTS | {".json", ".atlas", ".plist", ".fnt", ".ttf", ".otf"}

    def upload_asset(self, slug: str, path: str, data_b64: str, *, overwrite: bool = False) -> dict:
        self._ensure_write_enabled()
        project_dir = self._project_dir(slug)
        safe_path = _safe_relpath(path)
        if not safe_path:
            raise HTTPException(status_code=400, detail="Invalid asset path")
        ext = os.path.splitext(safe_path)[1].lower()
        if ext not in self._ASSET_ALLOWED_EXTS:
            raise HTTPException(status_code=400, detail=f"Unsupported asset type: {ext}")
        target = project_dir / safe_path
        if target.exists() and not overwrite:
            raise HTTPException(status_code=409, detail=f"Asset already exists, use overwrite=true: {safe_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw = base64.b64decode(data_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 data")
        target.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        return {
            "ok": True,
            "slug": slug,
            "path": safe_path,
            "size_bytes": len(raw),
            "sha256": sha,
            "overwritten": target.exists() and overwrite,
        }
