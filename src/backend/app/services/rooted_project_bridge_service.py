"""Generic rooted project bridge service for development providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
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


def _safe_relpath(value: str) -> str:
    text = (value or "").strip().replace("\\", "/").strip("/")
    if not text:
        return ""
    parts = [part for part in text.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise HTTPException(status_code=400, detail="Invalid path")
    return "/".join(parts)


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
        safe_slug = _safe_relpath(slug)
        if not safe_slug or "/" in safe_slug:
            raise HTTPException(status_code=400, detail="Invalid project slug")
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
        self._ensure_write_enabled()
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

    def build_project(self, slug: str, *, actor_user_id: str, summary: str | None = None) -> dict:
        self._ensure_write_enabled()
        project_dir = self._project_dir(slug)
        command = (self.config.build_command or "").strip()
        if not command:
            raise HTTPException(status_code=503, detail=f"{self.config.provider_key} build command not configured")
        build_id = uuid.uuid4().hex
        build_root = self._project_state_root(slug) / "builds" / build_id
        build_root.mkdir(parents=True, exist_ok=True)
        rendered = command.replace("{project_dir}", str(project_dir)).replace("{slug}", slug).replace("{build_id}", build_id)
        env = os.environ.copy()
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
        metadata = {
            "id": build_id,
            "provider": self.config.provider_key,
            "project": slug,
            "status": status_text,
            "command": rendered,
            "build_output_dir": str(build_dir) if build_dir.is_dir() else None,
            "snapshot_dir": snapshot_dir,
            "summary": (summary or "").strip() or None,
            "actor_user_id": actor_user_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "returncode": result.returncode,
        }
        (build_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        if result.returncode != 0:
            detail = f"Build failed with exit code {result.returncode}"
            stderr_tail = (result.stderr or "").strip()[-1500:]
            if stderr_tail:
                detail = f"{detail}\n{stderr_tail}"
            raise HTTPException(status_code=400, detail=detail)
        stdout_tail = (result.stdout or "").strip()[-2500:]
        return {"ok": True, "stdout_tail": stdout_tail or None, **metadata}

    def list_builds(self, slug: str) -> list[dict]:
        self._ensure_write_enabled()
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
        siblings = sorted(releases_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in siblings[keep:]:
            if old.is_dir():
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
