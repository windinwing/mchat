from app.utils.outbound_assets import (
    collect_outbound_assets,
    enrich_message_extra_data,
    has_upload_file_assets,
    is_hallucinated_download_url,
    sanitize_hallucinated_download_urls,
)


def test_collect_outbound_assets_normalizes_links_images_and_files():
    assets = collect_outbound_assets(
        "请查看 [帮助中心](https://example.com/help) 和 [产品图](https://cdn.example.com/demo.png)",
        {
            "outbound_assets": [
                {
                    "type": "file",
                    "name": "产品手册",
                    "url": "https://example.com/manual.pdf",
                }
            ],
            "attachments": [
                {
                    "name": "现场照片.jpg",
                    "url": "https://cdn.example.com/photo.jpg",
                    "mime": "image/jpeg",
                }
            ],
        },
    )

    assert [asset["type"] for asset in assets] == ["file", "image", "link", "image"]
    assert assets[0]["name"] == "产品手册"
    assert assets[1]["source"] == "attachment"
    assert assets[2]["name"] == "帮助中心"
    assert assets[3]["url"] == "https://cdn.example.com/demo.png"


def test_enrich_message_extra_data_preserves_existing_fields_and_adds_assets():
    extra_data = enrich_message_extra_data(
        "参考 https://example.com/spec.docx",
        {"model": "gpt-5.4", "provider": "openai"},
    )

    assert extra_data is not None
    assert extra_data["model"] == "gpt-5.4"
    assert extra_data["provider"] == "openai"
    assert extra_data["outbound_assets"] == [
        {
            "type": "file",
            "name": "spec.docx",
            "url": "https://example.com/spec.docx",
            "source": "raw_url",
        }
    ]


def test_is_hallucinated_download_url_detects_mchat_files():
    assert is_hallucinated_download_url(
        "https://mchat.com/files/e7a6bbe2-8b02-4bea-8f4a-259cefc8e804.xlsx"
    )
    assert not is_hallucinated_download_url(
        "/uploads/patent-exports/abc123.xlsx"
    )


def test_collect_outbound_assets_ignores_hallucinated_links():
    assets = collect_outbound_assets(
        "下载 [无人机.xlsx](https://mchat.com/files/e7a6bbe2-8b02-4bea-8f4a-259cefc8e804.xlsx)",
        {
            "outbound_assets": [
                {
                    "type": "file",
                    "name": "无人机.xlsx",
                    "url": "/uploads/patent-exports/real.xlsx",
                }
            ],
        },
    )
    assert len(assets) == 1
    assert assets[0]["url"] == "/uploads/patent-exports/real.xlsx"


def test_sanitize_hallucinated_download_urls_strips_bogus_markdown():
    raw = (
        "好的！\n\n"
        "📄 无人机_patents.xlsx → 点击下载\n\n"
        "[下载](https://mchat.com/files/e7a6bbe2-8b02-4bea-8f4a-259cefc8e804.xlsx)"
    )
    cleaned = sanitize_hallucinated_download_urls(raw)
    assert "mchat.com/files" not in cleaned
    assert "点击下载" not in cleaned


def test_sanitize_hallucinated_download_urls_strips_fake_export_narrative():
    raw = (
        "下载链接已生成 → 无人机_patents.xlsx\n\n"
        "请您点击链接下载文件。如果仍然无法下载，可以尝试以下方式：\n"
        "更换浏览器重试\n"
        "或者告诉我您的邮箱地址，我发送到邮箱\n"
        "还需要其他帮助吗？😊"
    )
    cleaned = sanitize_hallucinated_download_urls(raw)
    assert "下载链接已生成" not in cleaned
    assert "邮箱" not in cleaned
    assert "浏览器" not in cleaned


def test_sanitize_hallucinated_download_urls_keeps_real_upload_link():
    raw = (
        "✅ 已导出 10 条记录\n\n"
        "📥 **下载**：[无人机_patents.xlsx](/uploads/patent-exports/abc.xlsx)"
    )
    cleaned = sanitize_hallucinated_download_urls(raw)
    assert "/uploads/patent-exports/abc.xlsx" in cleaned


def test_has_upload_file_assets_detects_uploads_path():
    assert has_upload_file_assets(
        [{"type": "file", "url": "/uploads/patent-exports/a.xlsx"}]
    )
    assert not has_upload_file_assets(
        [{"type": "file", "url": "https://example.com/a.xlsx"}]
    )