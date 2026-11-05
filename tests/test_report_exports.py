from __future__ import annotations

import csv
from pathlib import Path

from app.database import database as database_module
from app.database.database import QADatabase
from qa_framework import mcp_tools


def _report_fixture(tmp_path: Path, monkeypatch) -> tuple[QADatabase, Path]:
    monkeypatch.setattr(database_module, "PROFILE_DB_DIR", tmp_path / "profiles")
    monkeypatch.setattr(mcp_tools, "QA_REPORTS_DIR", tmp_path / "reports")
    profile = "report-game"
    db = QADatabase.for_profile(profile)
    db.register_game(profile, "Report Game", "fmv")
    db.seed_testcases(profile, [{
        "case_id": "CASE-1", "title": "Choice should resolve", "scene_id": "SCENE-1",
        "source_sheet": "Flow", "source_row": 18, "expected": ["choice resolves"],
    }])
    existing = tmp_path / "evidence.png"
    existing.write_bytes(b"fixture evidence")
    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    run = {
        "run_id": "run-001", "profile": profile, "game": "Report Game",
        "game_type": "fmv", "steam_build_id": "build-9", "status": "COMPLETED",
        "qa_status": "UNASSERTED", "started_at_utc": "2026-10-11T00:00:00Z",
        "finished_at_utc": "2026-10-11T00:01:00Z", "manifest_path": str(manifest_path),
    }
    db.record_run(run, manifest_path)
    db.record_case_result(
        "run-001", "CASE-1", "UNASSERTED", expected=["choice resolves"],
        observed="No assertion mapping is configured.",
        evidence=[str(existing), str(tmp_path / "missing.png")],
    )
    db.record_feedback("feedback-1", "flow", "Check the left branch", "run-001", "CASE-1")
    return db, existing


def test_canonical_report_contains_source_feedback_and_evidence_status(tmp_path, monkeypatch) -> None:
    _db, existing = _report_fixture(tmp_path, monkeypatch)
    payload = mcp_tools.get_testcase_report_tool("run-001", "report-game")

    assert payload["qa_status"] == "UNASSERTED"
    assert payload["testcase_results"][0]["source"]["source_sheet"] == "Flow"
    assert payload["testcase_results"][0]["source"]["source_row"] == 18
    artifacts = payload["testcase_results"][0]["evidence_artifacts"]
    assert [item["status"] for item in artifacts] == ["available", "missing"]
    assert Path(artifacts[0]["path"]) == existing.resolve()
    assert payload["feedback"][0]["note"] == "Check the left branch"


def test_html_csv_and_docx_exports_use_canonical_manifest_and_no_fake_links(
    tmp_path, monkeypatch
) -> None:
    _report_fixture(tmp_path, monkeypatch)
    html_result = mcp_tools.export_testcase_report_html_tool("run-001", "report-game")
    csv_result = mcp_tools.export_testcase_report_csv_tool("run-001", "report-game")
    docx_result = mcp_tools.export_testcase_report_docx_tool("run-001", "report-game")

    html_path = Path(html_result["html_path"])
    html = html_path.read_text(encoding="utf-8")
    assert "CASE-1" in html and "Flow" in html and "row 18" in html
    assert "Check the left branch" in html
    assert "(missing)" in html
    assert "missing.png</a>" not in html
    assert html_result["qa_status"] == "UNASSERTED"

    with Path(csv_result["csv_path"]).open(encoding="utf-8-sig", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["qa_status"] == "UNASSERTED"
    assert row["source_sheet"] == "Flow" and row["source_row"] == "18"
    assert "[available]" in row["evidence"] and "[missing]" in row["evidence"]
    assert row["feedback"] == "flow: Check the left branch"

    from docx import Document

    doc = Document(docx_result["docx_path"])
    content = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "Flow" in content and "row 18" in content
    assert "Check the left branch" in content
    assert "[missing]" in content


def test_report_export_mcp_tools_are_registered() -> None:
    import asyncio

    from qa_framework.mcp_server import mcp

    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert {"export_testcase_report_html", "export_testcase_report_csv"} <= names
    assert {"get_fmv_coverage_report", "export_fmv_coverage_report"} <= names
    assert "get_unreal_performance_report" in names
