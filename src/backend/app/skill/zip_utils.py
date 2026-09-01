"""Utilities for validating and extracting skill zip archives."""

from __future__ import annotations

import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath

_MB = 1024 * 1024

# Keep these limits in one place so HTTP uploads, remote installs, the CLI, and
# direct extraction all enforce the same archive boundary.  The compressed
# limit matches the production reverse-proxy upload limit; the expanded limit
# prevents highly-compressible archives from bypassing tenant disk quotas.
SKILL_ZIP_MAX_ARCHIVE_BYTES = 50 * _MB
SKILL_ZIP_MAX_MEMBERS = 2048
SKILL_ZIP_MAX_UNCOMPRESSED_BYTES = 256 * _MB
SKILL_MD_MAX_BYTES = 1 * _MB


@dataclass(frozen=True)
class SkillZipInspection:
    """Validated archive metadata used by installers and quota checks."""

    skill_entry: str
    archive_size: int
    member_count: int
    uncompressed_size: int
    skill_md_size: int


def _normalize_zip_name(name: str) -> str:
    return name.replace("\\", "/")


def _validated_zip_name(name: str) -> str:
    """Return a canonical relative POSIX archive path or reject it."""
    norm = _normalize_zip_name(name)
    if not norm or "\x00" in norm:
        raise ValueError("Zip file contains an invalid path")
    if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        raise ValueError("Zip file contains an absolute path")
    path = PurePosixPath(norm)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Zip file contains a path outside the skill directory")
    return path.as_posix()


def _validate_archive_members(zf: zipfile.ZipFile) -> int:
    """Reject unsafe entries and return their total expanded byte count."""
    members = zf.infolist()
    if len(members) > SKILL_ZIP_MAX_MEMBERS:
        raise ValueError(
            f"Skill zip contains too many entries (max {SKILL_ZIP_MAX_MEMBERS})"
        )

    total_size = 0
    for member in members:
        _validated_zip_name(member.filename)
        unix_mode = (member.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(unix_mode):
            raise ValueError("Zip file contains a symbolic link")
        file_type = stat.S_IFMT(unix_mode)
        if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ValueError("Zip file contains an unsupported special file")
        total_size += member.file_size
        if total_size > SKILL_ZIP_MAX_UNCOMPRESSED_BYTES:
            raise ValueError(
                "Skill zip exceeds uncompressed size limit "
                f"({SKILL_ZIP_MAX_UNCOMPRESSED_BYTES // _MB} MB)"
            )
    return total_size


def inspect_skill_zip(content: bytes) -> SkillZipInspection:
    """Validate an archive without extracting it and return bounded metadata."""
    archive_size = len(content)
    if archive_size > SKILL_ZIP_MAX_ARCHIVE_BYTES:
        raise ValueError(
            "Skill zip exceeds compressed size limit "
            f"({SKILL_ZIP_MAX_ARCHIVE_BYTES // _MB} MB)"
        )

    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as e:
        raise ValueError("Invalid zip file") from e

    with zf:
        total_size = _validate_archive_members(zf)
        skill_entry = find_skill_md_entry(zf.namelist())
        if not skill_entry:
            raise ValueError("Zip file must contain SKILL.md")
        skill_info = zf.getinfo(skill_entry)
        if skill_info.file_size > SKILL_MD_MAX_BYTES:
            raise ValueError(
                f"SKILL.md exceeds size limit ({SKILL_MD_MAX_BYTES // _MB} MB)"
            )
        return SkillZipInspection(
            skill_entry=skill_entry,
            archive_size=archive_size,
            member_count=len(zf.infolist()),
            uncompressed_size=total_size,
            skill_md_size=skill_info.file_size,
        )


def find_skill_md_entry(names: list[str]) -> str | None:
    """Find SKILL.md inside a zip (root or nested), case-insensitive."""
    for raw in names:
        try:
            norm = _validated_zip_name(raw)
        except ValueError:
            continue
        if not norm or norm.endswith("/"):
            continue
        if "__MACOSX" in norm or "/." in norm:
            continue
        base = PurePosixPath(norm).name
        if base.lower() == "skill.md":
            return raw
    return None


def skill_root_prefix(skill_md_entry: str) -> str:
    """Directory prefix containing SKILL.md (POSIX, may be empty)."""
    norm = _validated_zip_name(skill_md_entry)
    parent = str(PurePosixPath(norm).parent)
    if parent in (".", ""):
        return ""
    return parent.rstrip("/") + "/"


def read_skill_meta_from_zip(content: bytes) -> dict[str, str]:
    """Read skill name from SKILL.md inside a zip without extracting to disk."""
    inspection = inspect_skill_zip(content)
    zf = zipfile.ZipFile(BytesIO(content))

    with zf:
        skill_entry = inspection.skill_entry

        prefix = skill_root_prefix(skill_entry)
        norm_entry = _validated_zip_name(skill_entry)
        folder_name = PurePosixPath(norm_entry).parent.name
        if folder_name in (".", ""):
            folder_name = PurePosixPath(
                prefix.rstrip("/") if prefix else norm_entry
            ).name

        try:
            raw = zf.read(skill_entry).decode("utf-8", errors="replace")
        except (zipfile.BadZipFile, RuntimeError) as e:
            raise ValueError("Invalid or unreadable SKILL.md") from e
    name = folder_name or "skill"
    description = ""

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].split("\n"):
                line = line.strip()
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip().lower()
                    value = value.strip().strip('"').strip("'")
                    if key == "name" and value:
                        name = value
                    elif key == "description" and value:
                        description = value

    return {"name": name, "description": description, "folder_hint": folder_name}


def extract_skill_zip(content: bytes, extract_path: Path) -> str:
    """Extract zip so SKILL.md ends up at extract_path/SKILL.md.

    Supports:
    - SKILL.md at zip root
    - my-skill/SKILL.md (single top-level folder)
    - ignores __MACOSX metadata

    Returns:
        The skill_md entry path inside the zip.

    Raises:
        ValueError: invalid zip or missing SKILL.md
    """
    inspection = inspect_skill_zip(content)
    zf = zipfile.ZipFile(BytesIO(content))

    if extract_path.is_symlink():
        zf.close()
        raise ValueError("Skill extraction path must not be a symbolic link")

    with zf:
        # Validate the entire archive before creating files. This also lets the
        # caller safely validate an update before deleting an existing skill.
        skill_entry = inspection.skill_entry

        prefix = skill_root_prefix(skill_entry)
        extract_root = extract_path.resolve()
        extract_root.mkdir(parents=True, exist_ok=True)

        for member in zf.infolist():
            raw_name = member.filename
            norm = _validated_zip_name(raw_name)
            if norm.endswith("/"):
                continue
            if "__MACOSX" in norm or "/." in norm:
                continue
            if prefix and not norm.startswith(prefix):
                continue
            relative = norm[len(prefix) :] if prefix else norm
            if not relative:
                continue
            target = (extract_root / relative).resolve()
            try:
                target.relative_to(extract_root)
            except ValueError as e:
                raise ValueError(
                    "Zip file contains a path outside the skill directory"
                ) from e
            if member.is_dir() or raw_name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)

    if not (extract_path / "SKILL.md").exists():
        # Case mismatch on disk (e.g. skill.md) — rename if found
        for child in extract_path.rglob("*"):
            if child.is_file() and child.name.lower() == "skill.md":
                child.rename(extract_path / "SKILL.md")
                break

    if not (extract_path / "SKILL.md").exists():
        raise ValueError("Failed to extract SKILL.md")

    return skill_entry


def _remove_install_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def install_skill_zip_atomic(content: bytes, target_dir: Path) -> str:
    """Fully extract to a sibling staging dir, then transactionally swap it in.

    Directory replacement needs two same-filesystem renames: the current
    install is first moved to a private backup, then the completed staging
    directory is moved into place.  Any failure before the second rename
    restores the backup, and all staging/backup paths are cleaned up.
    """
    target_dir = Path(target_dir)
    if target_dir.is_symlink():
        raise ValueError("Skill target directory must not be a symbolic link")
    if target_dir.exists() and not target_dir.is_dir():
        raise ValueError("Skill target path must be a directory")

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{target_dir.name}.staging-",
            dir=target_dir.parent,
        )
    )
    backup_dir = target_dir.parent / (
        f".{target_dir.name}.backup-{uuid.uuid4().hex}"
    )
    old_moved = False
    installed = False

    try:
        try:
            skill_entry = extract_skill_zip(content, staging_dir)
        except (zipfile.BadZipFile, RuntimeError) as e:
            raise ValueError("Invalid or unreadable skill zip") from e

        if target_dir.exists():
            target_dir.rename(backup_dir)
            old_moved = True

        try:
            staging_dir.rename(target_dir)
            installed = True
        except Exception:
            if old_moved and backup_dir.exists() and not target_dir.exists():
                backup_dir.rename(target_dir)
                old_moved = False
            raise

        return skill_entry
    finally:
        if staging_dir.exists() or staging_dir.is_symlink():
            _remove_install_path(staging_dir)
        if backup_dir.exists() or backup_dir.is_symlink():
            if not installed and not target_dir.exists():
                backup_dir.rename(target_dir)
            elif installed:
                # The new install is already live. A stale backup must not make
                # an otherwise successful install fail or replace the new tree.
                try:
                    _remove_install_path(backup_dir)
                except OSError:
                    pass
