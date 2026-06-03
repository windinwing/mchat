"""Skill service - business logic for skill management."""

from __future__ import annotations

import io
import ipaddress
import re
import shutil
import socket
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

from fastapi import HTTPException, UploadFile, status
import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.skill import Skill
from app.schemas.skill import SkillCatalogItem, SkillResponse, SkillUpdate
from app.skill.loader import SkillLoader
from app.skill.ops_policy import SCOPE_NOTIFICATION, SCOPE_SERVER_OPS, is_server_ops_skill
from app.skill.zip_utils import extract_skill_zip, read_skill_meta_from_zip


_BLOCKED_CIDR = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
]


def _is_url_safe(url: str) -> bool:
    """Check that a URL doesn't point to internal/private IPs (SSRF protection)."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        addr = ipaddress.ip_address(host)
        for net in _BLOCKED_CIDR:
            if addr in net:
                return False
        return True
    except ValueError:
        try:
            resolved = socket.getaddrinfo(host, None)
            for _, _, _, _, sockaddr in resolved:
                addr_str = sockaddr[0]
                addr = ipaddress.ip_address(addr_str)
                for net in _BLOCKED_CIDR:
                    if addr in net:
                        return False
        except (OSError, ValueError):
            return False
        return True


class SkillService:
    """Handles skill management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _skills_root(user_id: str) -> Path:
        from app.workspace.paths import ensure_execution_layout, tenant_skills_dir

        root = tenant_skills_dir(user_id)
        ensure_execution_layout(root.parent)
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _enforce_quota(user_id: str, *, additional_bytes: int = 0) -> None:
        from app.workspace.disk_usage import check_soft_quota
        from app.workspace.resolver import build_workspace_context

        ctx = build_workspace_context(user_id)
        message = check_soft_quota(ctx, additional_bytes=additional_bytes)
        if message:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=message,
            )

    @staticmethod
    def _skill_directory(skill: Skill) -> Path | None:
        if not skill.path:
            return None
        skill_md = Path(skill.path).resolve()
        if skill_md.is_file() and skill_md.name.lower() == "skill.md":
            return skill_md.parent
        if skill_md.is_dir():
            return skill_md
        return None

    def _is_managed_skill_dir(self, directory: Path, user_id: str) -> bool:
        """Only delete directories inside tenant skills or legacy global skills/."""
        try:
            directory.resolve().relative_to(self._skills_root(user_id))
            return True
        except ValueError:
            pass
        try:
            from app.core.skills_paths import resolve_skills_root

            directory.resolve().relative_to(resolve_skills_root())
            return True
        except ValueError:
            return False

    def _remove_skill_directory(self, skill: Skill) -> None:
        directory = self._skill_directory(skill)
        if directory is None or not directory.exists():
            return
        if not self._is_managed_skill_dir(directory, skill.user_id):
            logger.warning(f"Skip deleting skill dir outside managed roots: {directory}")
            return
        shutil.rmtree(directory)
        logger.info(f"Removed skill directory: {directory}")

    @staticmethod
    def _safe_folder_name(raw: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-._")
        return cleaned or "skill"

    @staticmethod
    def _looks_like_zip(content: bytes) -> bool:
        if len(content) < 4:
            return False
        if content[:2] != b"PK":
            return False
        try:
            return zipfile.is_zipfile(io.BytesIO(content))
        except Exception:
            return False

    @staticmethod
    def _extract_clawhub_download_url(html_text: str, page_url: str) -> str | None:
        matches = re.findall(r'href=["\']([^"\']+)["\']', html_text, flags=re.IGNORECASE)
        candidates: list[str] = []
        for href in matches:
            full = urljoin(page_url, href)
            lower = full.lower()
            if "/download" in lower or ".zip" in lower:
                candidates.append(full)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                "convex.site/api/v1/download" not in item.lower(),
                ".zip" not in item.lower(),
                len(item),
            )
        )
        return candidates[0]

    def _catalog_items_from_html(self, html_text: str) -> list[SkillCatalogItem]:
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html_text, flags=re.IGNORECASE)
        items: list[SkillCatalogItem] = []
        seen: set[str] = set()
        for href in hrefs:
            full = urljoin("https://clawhub.ai/skills", href)
            parsed = urlparse(full)
            path = (parsed.path or "").strip("/")
            parts = [part for part in path.split("/") if part]
            slug = ""
            homepage = ""
            if len(parts) == 2 and parts[0] == "skills":
                slug = self._safe_folder_name(parts[1])
                homepage = f"https://clawhub.ai/skills/{slug}"
            elif len(parts) == 2 and parts[0] not in {"assets", "plugins", "publishers", "audits", "api"}:
                slug = self._safe_folder_name(parts[1])
                homepage = f"https://clawhub.ai/{parts[0]}/{parts[1]}"
            if not slug or slug in seen:
                continue
            seen.add(slug)
            items.append(
                SkillCatalogItem(
                    name=slug,
                    title=slug,
                    homepage=homepage,
                )
            )
        return items

    async def _fetch_clawhub_skill_item(self, slug: str) -> SkillCatalogItem | None:
        safe_slug = self._safe_folder_name(slug)
        url = f"https://clawhub.ai/skills/{safe_slug}"
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(url)
            if resp.status_code >= 400:
                return None
            homepage = str(resp.url)
            html_text = resp.text
            title_match = re.search(r"<title>([^<]+)</title>", html_text, flags=re.IGNORECASE)
            title = (title_match.group(1).strip() if title_match else safe_slug).replace("| ClawHub", "").strip()
            download_url = self._extract_clawhub_download_url(html_text, homepage)
            return SkillCatalogItem(
                name=safe_slug,
                title=title or safe_slug,
                homepage=homepage,
                download_url=download_url,
            )
        except Exception:
            return None

    async def _install_skill_archive(
        self,
        *,
        user_id: str,
        content: bytes,
        source_name: str,
        name_hint: str | None = None,
    ) -> SkillResponse:
        skills_dir = self._skills_root(user_id)

        try:
            meta = read_skill_meta_from_zip(content)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

        skill_name = (
            str(meta.get("name") or "").strip()
            or (name_hint or "").strip()
            or Path(source_name).stem
        )
        folder_hint = str(meta.get("folder_hint") or "").strip()
        folder_base = (
            (name_hint or "").strip()
            or folder_hint
            or Path(source_name).stem
            or skill_name
        )
        install_folder = self._safe_folder_name(folder_base)

        result = await self.db.execute(
            select(Skill).where(
                Skill.user_id == user_id,
                Skill.name == skill_name,
            )
        )
        existing = result.scalar_one_or_none()

        if existing and existing.path:
            extract_path = self._skill_directory(existing) or (skills_dir / install_folder)
        else:
            extract_path = skills_dir / install_folder

        extract_path = extract_path.resolve()
        try:
            extract_path.relative_to(skills_dir)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid skill install path",
            ) from e

        if extract_path.exists():
            shutil.rmtree(extract_path)
        extract_path.mkdir(parents=True, exist_ok=True)

        self._enforce_quota(user_id, additional_bytes=len(content))

        try:
            extract_skill_zip(content, extract_path)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

        await self.reload_skills(user_id)

        result = await self.db.execute(
            select(Skill).where(
                Skill.user_id == user_id,
                Skill.path == str((extract_path / "SKILL.md").resolve()),
            )
        )
        skill = result.scalar_one_or_none()
        if skill is None:
            result = await self.db.execute(
                select(Skill).where(
                    Skill.user_id == user_id,
                    Skill.name == skill_name,
                )
            )
            skill = result.scalar_one_or_none()

        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Skill extracted to {extract_path.name} but not registered. "
                    "Please check SKILL.md metadata and run reload."
                ),
            )

        return SkillResponse.model_validate(skill)

    async def list_skills(self, user_id: str) -> list[SkillResponse]:
        """List all skills for a user."""
        result = await self.db.execute(
            select(Skill)
            .where(Skill.user_id == user_id)
            .order_by(Skill.created_at.desc())
        )
        skills = result.scalars().all()
        return [SkillResponse.model_validate(s) for s in skills]

    async def update_skill(
        self, skill_id: str, user_id: str, data: SkillUpdate
    ) -> SkillResponse | None:
        """Update a skill (enable/disable or config changes)."""
        result = await self.db.execute(
            select(Skill).where(
                Skill.id == skill_id, Skill.user_id == user_id
            )
        )
        skill = result.scalar_one_or_none()
        if skill is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(skill, key, value)

        await self.db.flush()
        await self.db.refresh(skill)
        return SkillResponse.model_validate(skill)

    async def delete_skill(
        self, skill_id: str, user_id: str
    ) -> bool:
        """Delete a skill from DB and remove its directory under skills/."""
        result = await self.db.execute(
            select(Skill).where(
                Skill.id == skill_id, Skill.user_id == user_id
            )
        )
        skill = result.scalar_one_or_none()
        if skill is None:
            return False
        if skill.skill_type == "builtin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete built-in skills",
            )
        self._remove_skill_directory(skill)
        await self.db.delete(skill)
        await self.db.flush()
        return True

    async def _prune_stale_filesystem_skills(self, user_id: str) -> int:
        """Remove DB rows whose SKILL.md path no longer exists on disk."""
        removed = 0
        result = await self.db.execute(
            select(Skill).where(Skill.user_id == user_id)
        )
        for skill in result.scalars().all():
            if skill.skill_type == "builtin" or not skill.path:
                continue
            skill_md = Path(skill.path)
            if not skill_md.is_file():
                await self.db.delete(skill)
                removed += 1
        if removed:
            await self.db.flush()
        return removed

    async def reload_skills(self, user_id: str) -> dict:
        """Sync DB with skills/ on disk: update existing, add new, drop stale."""
        await self._prune_stale_filesystem_skills(user_id)

        loader = SkillLoader(user_id=user_id)
        skills = loader.scan_skills()
        count = 0
        server_ops_names: list[str] = []
        for skill_data in skills:
            result = await self.db.execute(
                select(Skill).where(
                    Skill.user_id == user_id,
                    Skill.name == skill_data["name"],
                )
            )
            existing = result.scalar_one_or_none()
            disk_cfg = skill_data.get("config") or {}
            is_server_ops = (
                str(disk_cfg.get("scope") or "").strip().lower() == SCOPE_SERVER_OPS
            )
            is_notification = (
                str(disk_cfg.get("scope") or "").strip().lower() == SCOPE_NOTIFICATION
            )
            restricted = is_server_ops or is_notification
            if existing:
                existing.description = skill_data.get("description")
                existing.skill_type = skill_data.get("type", "tool")
                existing.path = skill_data.get("path")
                merged = dict(existing.config or {})
                merged.update(
                    {
                        k: v
                        for k, v in disk_cfg.items()
                        if k not in ("secrets", "env")
                    }
                )
                existing.config = merged
                if not restricted:
                    existing.enabled = True
            else:
                skill = Skill(
                    user_id=user_id,
                    name=skill_data["name"],
                    description=skill_data.get("description"),
                    skill_type=skill_data.get("type", "tool"),
                    path=skill_data.get("path"),
                    config=skill_data.get("config"),
                    enabled=False if restricted else True,
                )
                self.db.add(skill)
            if is_server_ops or (
                existing and is_server_ops_skill(existing)
            ):
                server_ops_names.append(skill_data["name"])
            count += 1

        if count > 0:
            await self.db.flush()
        return {
            "reloaded": count,
            "server_ops": sorted(set(server_ops_names)),
            "message": f"Reloaded {count} skills",
        }

    async def _download_archive(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"下载失败: {url} (HTTP {resp.status_code})",
                )
            content = resp.content
            if content and self._looks_like_zip(content):
                return content

            content_type = resp.headers.get("content-type", "").lower()
            if "html" in content_type or not self._looks_like_zip(content):
                archive_url = self._extract_clawhub_download_url(resp.text, str(resp.url))
                if archive_url and archive_url != url:
                    if not _is_url_safe(archive_url):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="不允许访问内网地址或保留 IP 地址",
                        )
                    archive_resp = await client.get(archive_url)
                    if archive_resp.status_code >= 400:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"下载失败: {archive_url} (HTTP {archive_resp.status_code})",
                        )
                    archive_content = archive_resp.content
                    if archive_content and self._looks_like_zip(archive_content):
                        return archive_content

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"下载内容不是有效 zip: {url}",
        )

    async def install_skill_from_url(
        self,
        *,
        user_id: str,
        url: str,
        name_hint: str | None = None,
    ) -> SkillResponse:
        target_url = (url or "").strip()
        if not target_url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL 必须以 http:// 或 https:// 开头",
            )
        if not _is_url_safe(target_url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不允许访问内网地址或保留 IP 地址",
            )

        content = await self._download_archive(target_url)
        parsed = urlparse(target_url)
        source_name = Path(parsed.path).name or "skill.zip"
        if not source_name.lower().endswith(".zip"):
            source_name = f"{source_name}.zip"
        return await self._install_skill_archive(
            user_id=user_id,
            content=content,
            source_name=source_name,
            name_hint=name_hint,
        )

    def _catalog_items_from_payload(self, payload: object) -> list[SkillCatalogItem]:
        rows: list[object] = []
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            for key in ("items", "skills", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    rows = value
                    break

        items: list[SkillCatalogItem] = []
        seen: set[str] = set()
        for row in rows:
            if isinstance(row, str):
                name = row.strip()
                if not name:
                    continue
                slug = self._safe_folder_name(name)
                if slug in seen:
                    continue
                seen.add(slug)
                items.append(
                    SkillCatalogItem(
                        name=slug,
                        title=name,
                        homepage=f"https://clawhub.ai/skills/{slug}",
                    )
                )
                continue

            if not isinstance(row, dict):
                continue

            raw_name = row.get("name") or row.get("slug") or row.get("id")
            if not raw_name:
                continue

            name = self._safe_folder_name(str(raw_name))
            if name in seen:
                continue

            title = str(row.get("title") or row.get("display_name") or name)
            description = row.get("description") or row.get("summary")
            homepage = row.get("homepage") or row.get("url")
            download_url = (
                row.get("download_url")
                or row.get("downloadUrl")
                or row.get("zip_url")
                or row.get("zipUrl")
            )

            if isinstance(homepage, str) and homepage.startswith("/"):
                homepage = f"https://clawhub.ai{homepage}"
            if isinstance(download_url, str) and download_url.startswith("/"):
                download_url = f"https://clawhub.ai{download_url}"
            if not homepage:
                homepage = f"https://clawhub.ai/skills/{name}"

            seen.add(name)
            items.append(
                SkillCatalogItem(
                    name=name,
                    title=title,
                    description=str(description) if description else None,
                    homepage=str(homepage) if homepage else None,
                    download_url=str(download_url) if download_url else None,
                )
            )

        return items

    async def fetch_clawhub_catalog(
        self,
        *,
        query: str | None = None,
        limit: int = 24,
    ) -> list[SkillCatalogItem]:
        urls = [
            "https://clawhub.ai/api/skills",
            "https://clawhub.ai/skills.json",
        ]

        items: list[SkillCatalogItem] = []
        for url in urls:
            try:
                async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                    resp = await client.get(url, headers={"Accept": "application/json"})
                if resp.status_code >= 400:
                    continue
                payload = resp.json()
                parsed = self._catalog_items_from_payload(payload)
                if parsed:
                    items = parsed
                    break
            except Exception:
                continue

        if not items:
            # HTML fallback: discover slugs from links.
            try:
                async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                    resp = await client.get("https://clawhub.ai/skills")
                items = self._catalog_items_from_html(resp.text)
            except Exception:
                items = []

        if not items:
            items = [
                SkillCatalogItem(
                    name="patent-search",
                    title="patent-search",
                    description="Patent search and analysis skill",
                    homepage="https://clawhub.ai/skills/patent-search",
                    download_url="https://clawhub.ai/skills/patent-search.zip",
                )
            ]

        needle = (query or "").strip().lower()
        if needle:
            items = [
                item
                for item in items
                if needle in item.name.lower()
                or needle in item.title.lower()
                or needle in (item.description or "").lower()
            ]
            if not items:
                exact = await self._fetch_clawhub_skill_item(needle)
                if exact is not None:
                    items = [exact]

        safe_limit = max(1, min(limit, 100))
        return items[:safe_limit]

    async def install_skill_by_name(
        self,
        *,
        user_id: str,
        name: str,
    ) -> SkillResponse:
        source = (name or "").strip()
        if not source:
            raise HTTPException(status_code=400, detail="技能名不能为空")
        if source.startswith(("http://", "https://")):
            return await self.install_skill_from_url(user_id=user_id, url=source)

        catalog = await self.fetch_clawhub_catalog(query=source, limit=20)
        matched = next(
            (
                item
                for item in catalog
                if item.name.lower() == source.lower()
                or item.title.lower() == source.lower()
            ),
            None,
        )

        candidate_urls: list[str] = []
        if matched and matched.download_url:
            candidate_urls.append(matched.download_url)
        if matched and matched.homepage:
            candidate_urls.append(matched.homepage)

        slug = self._safe_folder_name(source)
        candidate_urls.extend(
            [
                f"https://clawhub.ai/skills/{slug}",
                f"https://clawhub.ai/{slug}",
            ]
        )

        tried: list[str] = []
        for url in dict.fromkeys(candidate_urls):
            tried.append(url)
            try:
                return await self.install_skill_from_url(
                    user_id=user_id,
                    url=url,
                    name_hint=slug,
                )
            except HTTPException:
                continue

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"未能从 ClawHub 安装技能：{source}。"
                "请改用可直接下载的 zip URL。"
                f" 已尝试: {', '.join(tried)}"
            ),
        )

    async def list_skill_files(self, skill_id: str, user_id: str) -> list[dict]:
        """List all files in a skill directory."""
        result = await self.db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.user_id == user_id)
        )
        skill = result.scalar_one_or_none()
        if skill is None or not skill.path:
            raise HTTPException(status_code=404, detail="Skill not found")

        directory = self._skill_directory(skill)
        if directory is None or not directory.exists():
            return []

        files: list[dict] = []
        for fpath in sorted(directory.rglob("*")):
            if not fpath.is_file():
                continue
            rel = fpath.relative_to(directory)
            files.append({
                "path": str(rel),
                "name": fpath.name,
                "size": fpath.stat().st_size,
                "updated_at": fpath.stat().st_mtime,
            })
        return files

    async def read_skill_file(self, skill_id: str, user_id: str, file_path: str) -> dict:
        """Read a text file from a skill directory."""
        result = await self.db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.user_id == user_id)
        )
        skill = result.scalar_one_or_none()
        if skill is None or not skill.path:
            raise HTTPException(status_code=404, detail="Skill not found")

        directory = self._skill_directory(skill)
        if directory is None:
            raise HTTPException(status_code=404, detail="Skill directory not found")

        target = (directory / file_path).resolve()
        try:
            target.relative_to(directory)
        except ValueError:
            raise HTTPException(status_code=403, detail="Path traversal denied")

        if not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File is not a readable text file")

        return {
            "path": str(target.relative_to(directory)),
            "name": target.name,
            "content": content,
        }

    async def upload_skill_file(self, skill_id: str, user_id: str, file: UploadFile, relative_path: str = "") -> dict:
        """Upload a file into a skill directory."""
        result = await self.db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.user_id == user_id)
        )
        skill = result.scalar_one_or_none()
        if skill is None or not skill.path:
            raise HTTPException(status_code=404, detail="Skill not found")
        if skill.skill_type == "builtin":
            raise HTTPException(status_code=403, detail="Cannot modify built-in skills")

        directory = self._skill_directory(skill)
        if directory is None or not directory.exists():
            raise HTTPException(status_code=404, detail="Skill directory not found")

        file_name = relative_path.strip() or (file.filename or "untitled")
        target = (directory / file_name).resolve()
        try:
            target.relative_to(directory)
        except ValueError:
            raise HTTPException(status_code=403, detail="Path traversal denied")

        target.parent.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        self._enforce_quota(user_id, additional_bytes=len(content))
        target.write_bytes(content)
        return {"path": str(target.relative_to(directory)), "name": target.name, "written": True}

    async def write_skill_file(self, skill_id: str, user_id: str, file_path: str, content: str) -> dict:
        """Write a text file in a skill directory."""
        result = await self.db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.user_id == user_id)
        )
        skill = result.scalar_one_or_none()
        if skill is None or not skill.path:
            raise HTTPException(status_code=404, detail="Skill not found")
        if skill.skill_type == "builtin":
            raise HTTPException(status_code=403, detail="Cannot edit built-in skills")

        directory = self._skill_directory(skill)
        if directory is None or not directory.exists():
            raise HTTPException(status_code=404, detail="Skill directory not found")

        target = (directory / file_path).resolve()
        try:
            target.relative_to(directory)
        except ValueError:
            raise HTTPException(status_code=403, detail="Path traversal denied")

        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        self._enforce_quota(user_id, additional_bytes=len(encoded))
        target.write_text(content, encoding="utf-8")
        return {"path": str(target.relative_to(directory)), "name": target.name, "written": True}

    async def create_skill(
        self, *, user_id: str, name: str, description: str | None = None, skill_type: str = "tool"
    ) -> SkillResponse:
        """Create a new skill directory with a minimal SKILL.md."""
        skills_dir = self._skills_root(user_id)

        folder_name = self._safe_folder_name(name)
        skill_dir = skills_dir / folder_name

        if skill_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Skill directory already exists: {folder_name}",
            )

        skill_dir.mkdir(parents=True, exist_ok=True)

        desc = (description or "").strip()
        frontmatter = f"---\nname: {name}\n"
        if desc:
            frontmatter += f"description: \"{desc}\"\n"
        frontmatter += f"type: {skill_type}\n---\n"

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(frontmatter, encoding="utf-8")

        await self.reload_skills(user_id)

        result = await self.db.execute(
            select(Skill).where(
                Skill.user_id == user_id,
                Skill.name == name,
            )
        )
        skill = result.scalar_one_or_none()
        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Skill created on disk but not registered. Check SKILL.md metadata.",
            )
        return SkillResponse.model_validate(skill)

    async def upload_skill(
        self, user_id: str, file: UploadFile
    ) -> SkillResponse:
        """Upload a skill zip; overwrites same-name skill directory on disk."""
        content = await file.read()
        return await self._install_skill_archive(
            user_id=user_id,
            content=content,
            source_name=file.filename or "skill.zip",
        )
