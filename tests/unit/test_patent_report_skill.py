"""Unit tests for patent-report skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.core.skills_paths import resolve_skill_directory


def _skill_dir() -> Path | None:
    resolved = resolve_skill_directory("patent-report")
    if resolved is not None:
        return resolved
    fallback = Path(__file__).resolve().parents[2] / "skills" / "patent-report"
    return fallback if (fallback / "SKILL.md").is_file() else None


def _load_module(name: str, filename: str, skill_dir: Path):
    path = skill_dir / filename
    if not path.is_file():
        pytest.skip(f"missing {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def patent_report_dir() -> Path:
    skill_dir = _skill_dir()
    if skill_dir is None:
        pytest.skip(
            "patent-report not found — set EXTRA_SKILLS_DIRS to your patent skills repo"
        )
    return skill_dir


def test_normalize_sections_from_merge_payload(patent_report_dir: Path):
    sections_mod = _load_module("patent_report_sections", "sections.py", patent_report_dir)
    raw = {
        "申请人分析": {
            "node_id": "applicant",
            "result": {
                "message": "| 排名 | 申请人 | 数量 |\n| --- | --- | --- |\n| 1 | 华为 | 120 |\n| 2 | 大疆 | 80 |"
            },
        }
    }
    out = sections_mod.normalize_sections(raw)
    assert len(out) == 1
    assert out[0]["title"] == "申请人分析"
    assert len(out[0]["rows"]) == 2
    assert out[0]["rows"][0]["label"] == "华为"
    assert out[0]["rows"][0]["value"] == 120.0


def test_run_chart_and_excel(tmp_path, monkeypatch, patent_report_dir: Path):
    monkeypatch.setenv("MCHAT_UPLOAD_DIR", str(tmp_path))
    main_mod = _load_module("patent_report_main", "main.py", patent_report_dir)
    sections = {
        "年份趋势": {
            "result": {
                "rows": [
                    {"label": "2022", "value": 10},
                    {"label": "2023", "value": 20},
                ]
            }
        }
    }
    chart_result = main_mod.run(command="chart", sections=sections, title="Drone")
    assert chart_result["ok"] is True
    assert chart_result["charts"]
    assert Path(chart_result["charts"][0]["path"]).is_file()

    excel_result = main_mod.run(
        command="excel",
        sections=sections,
        title="Drone",
        filename="drone-report",
    )
    assert excel_result["ok"] is True
    assert any(f["format"] == "xlsx" for f in excel_result["files"])


@pytest.mark.skipif(
    importlib.util.find_spec("pptx") is None,
    reason="python-pptx not installed",
)
def test_run_all_bundle(tmp_path, monkeypatch, patent_report_dir: Path):
    monkeypatch.setenv("MCHAT_UPLOAD_DIR", str(tmp_path))
    main_mod = _load_module("patent_report_main_all", "main.py", patent_report_dir)
    sections = {
        "区域分布": {
            "result": {
                "rows": [
                    {"label": "广东", "value": 30},
                    {"label": "北京", "value": 15},
                ]
            }
        }
    }
    result = main_mod.run(
        command="all",
        sections=sections,
        title="Test Report",
        filename="test-report",
    )
    assert result["ok"] is True
    formats = {f["format"] for f in result["files"]}
    assert {"png", "xlsx", "docx", "pptx"}.issubset(formats)
