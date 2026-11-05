from __future__ import annotations

from pathlib import Path

import pytest

from qa_framework.mcp_tools import get_testcase_report_tool, run_robot_suite_tool


def test_mcp_robot_tool_runs_tagged_suite_and_returns_artifacts(tmp_path: Path) -> None:
    pytest.importorskip("robot")
    suite = tmp_path / "agent_suite.robot"
    suite.write_text(
        "*** Test Cases ***\n"
        "Robot Tool Smoke\n"
        "    [Tags]    smoke    fmv\n"
        "    Should Be Equal    1    1\n",
        encoding="utf-8",
    )

    result = run_robot_suite_tool(
        str(suite),
        include_tags=["smoke"],
        variables=["PROFILE:highschoolblood-demo"],
        output_dir=str(tmp_path / "runs"),
    )

    assert result["status"] == "PASS"
    assert result["robot_status"] == "PASS"
    assert result["qa_status"] == "UNASSERTED"
    assert result["test_count"] == 1
    assert Path(result["report_html"]).is_file()
    assert Path(result["output_xml"]).is_file()
    assert Path(result["manifest_path"]).is_file()


def test_mcp_robot_tool_rejects_missing_suite(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        run_robot_suite_tool(str(tmp_path / "missing.robot"))


def test_mcp_robot_tool_bounds_timeout(tmp_path: Path) -> None:
    suite = tmp_path / "suite.robot"
    suite.write_text("*** Test Cases ***\nNoop\n    No Operation\n", encoding="utf-8")
    with pytest.raises(ValueError, match="timeout_sec"):
        run_robot_suite_tool(str(suite), timeout_sec=7201)


def test_mcp_robot_tool_syncs_explicit_case_tag_to_profile_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("robot")
    from app.database.database import QADatabase

    database = QADatabase(tmp_path / "qa_profile.sqlite3")
    database.register_game("robot-fixture", "Robot Fixture", "fmv_visual_novel")
    database.seed_testcases(
        "robot-fixture", [{"case_id": "TC-ROBOT-01", "title": "Screen assertion"}]
    )
    monkeypatch.setattr(
        QADatabase,
        "for_profile",
        classmethod(lambda cls, profile: database),
    )
    suite = tmp_path / "mapped.robot"
    suite.write_text(
        "*** Test Cases ***\n"
        "Visible state is valid\n"
        "    [Tags]    case:TC-ROBOT-01    smoke\n"
        "    Should Be Equal    menu    menu\n",
        encoding="utf-8",
    )

    result = run_robot_suite_tool(
        str(suite),
        profile="robot-fixture",
        game_type="fmv_visual_novel",
        output_dir=str(tmp_path / "runs"),
    )

    assert result["qa_status"] == "PASS"
    assert result["database_sync"]["status"] == "SYNCED"
    assert result["database_sync"]["mapped_test_count"] == 1
    stored_runs = database.list_runs(profile="robot-fixture")
    assert stored_runs[0]["run_id"] == result["run_id"]
    assert stored_runs[0]["qa_status"] == "PASS"
    stored_results = database.list_testcase_results(result["run_id"])
    assert stored_results[0]["case_id"] == "TC-ROBOT-01"
    assert stored_results[0]["status"] == "PASS"
    assert stored_results[0]["assertions"][0]["source"] == "Robot Framework"
    assert all(Path(item).is_file() for item in stored_results[0]["evidence"] if item)
    report = get_testcase_report_tool(result["run_id"], profile="robot-fixture")
    assert report["qa_status"] == "PASS"
    assert report["testcase_results"][0]["case_id"] == "TC-ROBOT-01"

    unmapped_suite = tmp_path / "unmapped.robot"
    unmapped_suite.write_text(
        "*** Test Cases ***\nUnmapped assertion\n    Should Be Equal    menu    menu\n",
        encoding="utf-8",
    )
    unmapped = run_robot_suite_tool(
        str(unmapped_suite),
        profile="robot-fixture",
        output_dir=str(tmp_path / "unmapped-runs"),
    )
    assert unmapped["robot_status"] == "PASS"
    assert unmapped["qa_status"] == "UNASSERTED"
    assert unmapped["database_sync"]["status"] == "PARTIAL"
    assert database.list_testcase_results(unmapped["run_id"]) == []
