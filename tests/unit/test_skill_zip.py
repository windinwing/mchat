"""Tests for skill zip extraction."""

import stat
import zipfile
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from app.models.user import User
from app.services.skill_service import (
    SkillService,
    _is_trusted_tenant_skill_url,
)
from app.skill import zip_utils
from app.skill.zip_utils import (
    extract_skill_zip,
    find_skill_md_entry,
    inspect_skill_zip,
    install_skill_zip_atomic,
)


def _make_zip(files: dict[str, str | bytes]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_find_skill_md_at_root():
    names = ["SKILL.md", "handler.py"]
    assert find_skill_md_entry(names) == "SKILL.md"


def test_find_skill_md_in_subfolder():
    names = ["my-skill/SKILL.md", "my-skill/handler.py"]
    assert find_skill_md_entry(names) == "my-skill/SKILL.md"


def test_find_skill_md_case_insensitive():
    names = ["folder/skill.md"]
    assert find_skill_md_entry(names) == "folder/skill.md"


def test_extract_nested_folder(tmp_path: Path):
    content = _make_zip(
        {
            "demo-skill/SKILL.md": "---\nname: demo-skill\ndescription: test\n---\n",
            "demo-skill/handler.py": "# handler\n",
        }
    )
    target = tmp_path / "demo-skill"
    extract_skill_zip(content, target)
    assert (target / "SKILL.md").exists()
    assert (target / "handler.py").exists()


@pytest.mark.parametrize(
    "malicious_name",
    [
        "demo-skill/../../escaped.txt",
        "demo-skill\\..\\..\\escaped.txt",
        "/tmp/mchat-escaped.txt",
        "C:/mchat-escaped.txt",
    ],
)
def test_extract_rejects_unsafe_member_paths(
    tmp_path: Path, malicious_name: str
):
    content = _make_zip(
        {
            "demo-skill/SKILL.md": "---\nname: demo-skill\n---\n",
            malicious_name: "escaped",
        }
    )
    target = tmp_path / "demo-skill"

    with pytest.raises(ValueError, match="path"):
        extract_skill_zip(content, target)

    assert not (tmp_path / "escaped.txt").exists()


def test_extract_rejects_symbolic_link_members(tmp_path: Path):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("demo-skill/SKILL.md", "---\nname: demo-skill\n---\n")
        link = zipfile.ZipInfo("demo-skill/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, "../../escaped.txt")

    with pytest.raises(ValueError, match="symbolic link"):
        extract_skill_zip(buf.getvalue(), tmp_path / "demo-skill")


def test_extract_rejects_symbolic_link_destination(tmp_path: Path):
    content = _make_zip(
        {"SKILL.md": "---\nname: demo-skill\n---\n"}
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "demo-skill"
    target.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="extraction path"):
        extract_skill_zip(content, target)

    assert not (outside / "SKILL.md").exists()


def test_rejects_compressed_archive_over_limit(monkeypatch):
    content = _make_zip({"SKILL.md": "---\nname: demo\n---\n"})
    monkeypatch.setattr(zip_utils, "SKILL_ZIP_MAX_ARCHIVE_BYTES", len(content) - 1)

    with pytest.raises(ValueError, match="compressed size"):
        inspect_skill_zip(content)


def test_rejects_too_many_archive_members(monkeypatch):
    content = _make_zip(
        {
            "SKILL.md": "---\nname: demo\n---\n",
            "handler.py": "# handler\n",
        }
    )
    monkeypatch.setattr(zip_utils, "SKILL_ZIP_MAX_MEMBERS", 1)

    with pytest.raises(ValueError, match="too many entries"):
        inspect_skill_zip(content)


def test_rejects_zip_bomb_by_total_uncompressed_size(monkeypatch):
    content = _make_zip(
        {
            "SKILL.md": "---\nname: demo\n---\n",
            "payload.bin": b"0" * 4096,
        }
    )
    monkeypatch.setattr(zip_utils, "SKILL_ZIP_MAX_UNCOMPRESSED_BYTES", 1024)

    with pytest.raises(ValueError, match="uncompressed size"):
        inspect_skill_zip(content)


def test_rejects_oversized_skill_md(monkeypatch):
    content = _make_zip({"SKILL.md": "---\nname: demo\n---\n"})
    monkeypatch.setattr(zip_utils, "SKILL_MD_MAX_BYTES", 8)

    with pytest.raises(ValueError, match="SKILL.md exceeds"):
        inspect_skill_zip(content)


def _zip_with_corrupt_later_member() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("demo/SKILL.md", "---\nname: demo\n---\n")
        zf.writestr("demo/payload.bin", bytes(range(256)) * 4)

    raw = bytearray(buf.getvalue())
    with zipfile.ZipFile(BytesIO(raw)) as zf:
        info = zf.getinfo("demo/payload.bin")
        offset = info.header_offset
        name_len = int.from_bytes(raw[offset + 26 : offset + 28], "little")
        extra_len = int.from_bytes(raw[offset + 28 : offset + 30], "little")
        data_offset = offset + 30 + name_len + extra_len
        raw[data_offset + info.file_size // 2] ^= 0x80
    return bytes(raw)


def test_atomic_install_failure_preserves_old_skill_and_cleans_staging(tmp_path: Path):
    target = tmp_path / "demo"
    target.mkdir()
    old_file = target / "old.txt"
    old_file.write_text("keep me", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid or unreadable"):
        install_skill_zip_atomic(_zip_with_corrupt_later_member(), target)

    assert old_file.read_text(encoding="utf-8") == "keep me"
    assert not list(tmp_path.glob(".demo.staging-*"))
    assert not list(tmp_path.glob(".demo.backup-*"))


def test_atomic_install_replaces_old_skill_after_complete_extraction(tmp_path: Path):
    target = tmp_path / "demo"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    content = _make_zip(
        {
            "demo/SKILL.md": "---\nname: demo\n---\n",
            "demo/handler.py": "# new handler\n",
        }
    )

    install_skill_zip_atomic(content, target)

    assert not (target / "old.txt").exists()
    assert (target / "SKILL.md").is_file()
    assert (target / "handler.py").read_text(encoding="utf-8") == "# new handler\n"
    assert not list(tmp_path.glob(".demo.staging-*"))
    assert not list(tmp_path.glob(".demo.backup-*"))


def test_cli_install_failure_preserves_old_skill(tmp_path: Path):
    from app.cli import _extract_skill_zip_to

    target = tmp_path / "demo"
    target.mkdir()
    old_file = target / "old.txt"
    old_file.write_text("keep me", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Invalid or unreadable"):
        _extract_skill_zip_to(_zip_with_corrupt_later_member(), target)

    assert old_file.read_text(encoding="utf-8") == "keep me"


def test_tenant_skill_source_allowlist_requires_https_registry_hosts():
    assert _is_trusted_tenant_skill_url("https://clawhub.ai/skills/demo")
    assert _is_trusted_tenant_skill_url("https://registry.convex.site/api/download")
    assert not _is_trusted_tenant_skill_url("http://clawhub.ai/skills/demo")
    assert not _is_trusted_tenant_skill_url("https://clawhub.ai.evil.example/demo")
    assert not _is_trusted_tenant_skill_url("https://example.com/demo.zip")


@pytest.mark.asyncio
async def test_tenant_cannot_install_from_arbitrary_public_url(
    db_session, monkeypatch
):
    tenant = User(
        id="skill-url-tenant",
        username="skill-url-tenant",
        password_hash="x",
        role="agent",
    )
    db_session.add(tenant)
    await db_session.flush()
    monkeypatch.setattr(
        "app.services.skill_service._is_url_safe",
        lambda _url: True,
    )

    service = SkillService(db_session)
    with pytest.raises(HTTPException) as denied:
        await service.install_skill_from_url(
            user_id=tenant.id,
            url="https://example.com/demo.zip",
        )

    assert denied.value.status_code == 400
    assert "ClawHub" in denied.value.detail


@pytest.mark.asyncio
async def test_skill_download_revalidates_redirect_target(db_session):
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/internal.zip"},
            request=request,
        )

    service = SkillService(db_session)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
    ) as client:
        with pytest.raises(HTTPException) as denied:
            await service._download_archive_candidate(
                client,
                "http://8.8.8.8/demo.zip",
            )

    assert denied.value.status_code == 400
    assert requested == ["http://8.8.8.8/demo.zip"]


@pytest.mark.asyncio
async def test_tenant_skill_download_rejects_redirect_outside_registry(
    db_session, monkeypatch
):
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "https://evil.example/demo.zip"},
            request=request,
        )

    monkeypatch.setattr(
        "app.services.skill_service._is_url_safe",
        lambda _url: True,
    )
    service = SkillService(db_session)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
    ) as client:
        with pytest.raises(HTTPException) as denied:
            await service._download_archive_candidate(
                client,
                "https://clawhub.ai/skills/demo",
                trusted_tenant_source=True,
            )

    assert denied.value.status_code == 400
    assert requested == ["https://clawhub.ai/skills/demo"]
