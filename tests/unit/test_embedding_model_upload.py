import stat
import zipfile
from pathlib import Path

import pytest

from app.services.embedding_model_service import (
    _resolve_model_root,
    _validate_model_dir,
)


def test_validate_model_dir_requires_marker(tmp_path):
    (tmp_path / "readme.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="未识别"):
        _validate_model_dir(tmp_path)

    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    _validate_model_dir(tmp_path)


def test_resolve_model_root_single_folder(tmp_path):
    inner = tmp_path / "my-model"
    inner.mkdir()
    (inner / "config.json").write_text("{}", encoding="utf-8")
    assert _resolve_model_root(tmp_path) == inner


def test_safe_zip_layout(tmp_path):
    zpath = tmp_path / "m.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("model/config.json", "{}")
    extract = tmp_path / "out"
    extract.mkdir()
    from app.services.embedding_model_service import _safe_extract_zip

    _safe_extract_zip(zpath, extract)
    assert (extract / "model" / "config.json").is_file()


@pytest.mark.parametrize(
    "member_name",
    ["../escaped", "model/../../escaped", "model\\..\\escaped", "/tmp/escaped", "C:/escaped"],
)
def test_safe_zip_rejects_unsafe_paths(tmp_path, member_name):
    zpath = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("model/config.json", "{}")
        zf.writestr(member_name, "escaped")

    from app.services.embedding_model_service import _safe_extract_zip

    with pytest.raises(ValueError, match="路径"):
        _safe_extract_zip(zpath, tmp_path / "out")
    assert not (tmp_path / "escaped").exists()


def test_safe_zip_rejects_symbolic_link(tmp_path):
    zpath = tmp_path / "symlink.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("model/config.json", "{}")
        link = zipfile.ZipInfo("model/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, "../../escaped")

    from app.services.embedding_model_service import _safe_extract_zip

    with pytest.raises(ValueError, match="符号链接"):
        _safe_extract_zip(zpath, tmp_path / "out")


def test_safe_zip_rejects_symbolic_link_destination(tmp_path):
    zpath = tmp_path / "model.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("model/config.json", "{}")
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "out"
    destination.symlink_to(outside, target_is_directory=True)

    from app.services.embedding_model_service import _safe_extract_zip

    with pytest.raises(ValueError, match="解压目录"):
        _safe_extract_zip(zpath, destination)
    assert not (outside / "model" / "config.json").exists()
