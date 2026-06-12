"""Upload path resolution and traversal guard."""

from pathlib import Path

from app.utils.upload_paths import safe_upload_file_path


def test_safe_upload_file_path_blocks_traversal(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "chat").mkdir()
    (root / "chat" / "ok.txt").write_text("x", encoding="utf-8")

    ok = safe_upload_file_path("chat/ok.txt", root=root)
    assert ok is not None and ok.read_text(encoding="utf-8") == "x"

    assert safe_upload_file_path("../etc/passwd", root=root) is None
    assert safe_upload_file_path("chat/../../etc/passwd", root=root) is None
