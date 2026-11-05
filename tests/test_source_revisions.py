from __future__ import annotations

import sqlite3
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
import pytest

from app.database.database import QADatabase
from app.qa import workbook_import


def _db(tmp_path: Path) -> QADatabase:
    db = QADatabase(tmp_path / "qa.sqlite3")
    db.register_game("game-a", "Game A", "fmv_visual_novel")
    db.register_game("game-b", "Game B", "fmv_visual_novel")
    return db


def _sheets(rows: list[list[object]]) -> list[dict[str, object]]:
    return [{
        "sheet_name": "Flow",
        "rows": rows,
        "row_count": len(rows),
        "column_count": max((len(row) for row in rows), default=0),
        "hyperlinks": [],
    }]


def test_source_snapshot_sync_is_idempotent_and_citable(tmp_path: Path) -> None:
    db = _db(tmp_path)
    sheets = _sheets([["Flow", "Target"], ["Scene A", "Scene B"]])
    first = db.sync_source_snapshot("game-a", "sheet-1", "Flow workbook", sheets, source_url="https://example.test/sheet")
    second = db.sync_source_snapshot("game-a", "sheet-1", "Flow workbook", sheets, source_url="https://example.test/sheet")

    assert first["changed"] is True
    assert second["changed"] is False
    assert first["revision_hash"] == second["revision_hash"]
    revisions = db.list_source_revisions("game-a", "sheet-1")
    assert len(revisions) == 1
    assert revisions[0]["status"] == "current"
    rows = db.list_source_revision_rows("game-a", "sheet-1")
    assert [(row["row_number"], row["payload"]) for row in rows] == [
        (1, ["Flow", "Target"]),
        (2, ["Scene A", "Scene B"]),
    ]
    assert rows[1]["row_hash"]


def test_changed_snapshot_keeps_history_and_exposes_only_current_rows(tmp_path: Path) -> None:
    db = _db(tmp_path)
    old = db.sync_source_snapshot("game-a", "sheet-1", "Flow workbook", _sheets([["A"], ["B"]]))
    new = db.sync_source_snapshot("game-a", "sheet-1", "Flow workbook", _sheets([["A2"]]))

    assert new["changed"] is True
    assert new["previous_revision_hash"] == old["revision_hash"]
    revisions = db.list_source_revisions("game-a", "sheet-1")
    assert [revision["status"] for revision in revisions] == ["superseded", "current"]
    assert [row["payload"] for row in db.list_source_revision_rows("game-a", "sheet-1")] == [["A2"]]
    assert [row["payload"] for row in db.list_source_revision_rows("game-a", "sheet-1", old["revision_hash"])] == [["A"], ["B"]]
    assert [sheet["rows"] for sheet in db.list_source_sheets("game-a", include_rows=True)] == [[["A2"]]]


def test_revision_rows_can_be_filtered_to_one_sheet(tmp_path: Path) -> None:
    db = _db(tmp_path)
    sheets = _sheets([["Flow"], ["Scene A"]])
    sheets.append({
        "sheet_name": "Subtitles", "rows": [["Key"], ["line-1"]],
        "row_count": 2, "column_count": 1, "hyperlinks": [],
    })
    result = db.sync_source_snapshot("game-a", "sheet-multi", "Workbook", sheets)

    assert len(db.list_source_revision_rows("game-a", "sheet-multi", result["revision_hash"])) == 4
    assert [row["payload"] for row in db.list_source_revision_rows(
        "game-a", "sheet-multi", result["revision_hash"], sheet_name="Subtitles"
    )] == [["Key"], ["line-1"]]


def test_snapshot_failure_rolls_back_revision_and_sheet_replacement(tmp_path: Path) -> None:
    db = _db(tmp_path)
    old = db.sync_source_snapshot("game-a", "sheet-1", "Flow workbook", _sheets([["old"]]))
    with db._connect() as connection:  # noqa: SLF001 - inject a transaction failure
        connection.execute(
            """CREATE TRIGGER abort_source_row BEFORE INSERT ON source_revision_rows
               BEGIN SELECT RAISE(ABORT, 'injected failure'); END"""
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        db.sync_source_snapshot("game-a", "sheet-1", "Flow workbook", _sheets([["new"]]))

    assert db.list_source_revisions("game-a", "sheet-1")[0]["revision_hash"] == old["revision_hash"]
    assert [row["payload"] for row in db.list_source_revision_rows("game-a", "sheet-1")] == [["old"]]
    assert [sheet["rows"] for sheet in db.list_source_sheets("game-a", include_rows=True)] == [[["old"]]]


def test_source_history_is_scoped_to_game_profile(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.sync_source_snapshot("game-a", "shared-id", "Workbook", _sheets([["A"]]))
    assert db.list_source_revisions("game-b", "shared-id") == []
    assert db.list_source_revision_rows("game-b", "shared-id") == []


def test_workbook_import_commits_snapshot_and_graph_together(tmp_path: Path) -> None:
    db = _db(tmp_path)
    kwargs = {
        "profile": "game-a",
        "display_name": "Game A",
        "game_type": "fmv_visual_novel",
        "source_id": "sheet-atomic",
        "source_name": "Flow workbook",
        "source_url": "https://example.test/flow",
        "sheets": _sheets([["Flow", "Target"], ["A", "B"]]),
        "scenes": [
            {"scene_id": "scene-a", "group": "Flow"},
            {"scene_id": "scene-b", "group": "Flow"},
        ],
        "links": [{"source": "scene-a", "target": "scene-b", "choice_key": "Go Left"}],
        "cases": [{"case_id": "case-1", "scene_id": "scene-a", "source_row": 2}],
        "cues": [{
            "scene_id": "scene-a", "key": "cue-1", "start": 0, "end": 1,
            "translations": {"en": "A known line"}, "source_sheet": "Subtitles",
        }],
        "choices": [{
            "scene_id": "scene-a", "key": "choice-1",
            "translations": {"en": "Go Left"}, "source_sheet": "Choices",
        }],
    }
    result = db.sync_workbook_import(**kwargs)
    assert result["changed"] is True
    assert len(db.list_story_scenes("game-a")) == 2
    project = db.load_story_project("game-a")
    assert project is not None
    assert project["scenes"]["scene-a"]["outgoing"] == [
        {"target": "scene-b", "choice_key": "Go Left"}
    ]
    assert len(db.list_testcase_sources("game-a")) == 1
    assert len(db.list_source_revision_rows("game-a", "sheet-atomic")) == 2
    provenance = db.list_source_entity_provenance("game-a", source_id="sheet-atomic")
    assert {row["entity_type"] for row in provenance} == {
        "scene", "link", "testcase", "cue", "choice"
    }
    assert all(row["status"] == "active" for row in provenance)

    second = db.sync_workbook_import(**kwargs)
    assert second["changed"] is False
    assert second["flow_scenes_added"] == 0
    assert second["flow_links_added"] == 0
    assert len(db.list_story_scenes("game-a")) == 2
    assert len(db.list_source_revisions("game-a", "sheet-atomic")) == 1


def test_workbook_graph_failure_rolls_back_revision_and_all_entities(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with db._connect() as connection:  # noqa: SLF001 - inject a transaction failure
        connection.execute(
            """CREATE TRIGGER abort_choice BEFORE INSERT ON story_choices
               BEGIN SELECT RAISE(ABORT, 'injected graph failure'); END"""
        )
    kwargs = {
        "profile": "transaction-game",
        "display_name": "Transaction Game",
        "game_type": "fmv_visual_novel",
        "source_id": "sheet-failure",
        "source_name": "Workbook",
        "source_url": "https://example.test/failure",
        "sheets": _sheets([["source row"]]),
        "scenes": [{"scene_id": "scene-a", "group": "Flow"}],
        "links": [],
        "cases": [],
        "cues": [],
        "choices": [{
            "scene_id": "scene-a", "key": "choice-1",
            "translations": {"en": "Go Left"}, "source_sheet": "Choices",
        }],
    }
    with pytest.raises(sqlite3.IntegrityError, match="injected graph failure"):
        db.sync_workbook_import(**kwargs)

    assert db.list_games() == [
        {"profile": "game-a", "display_name": "Game A", "game_type": "fmv_visual_novel"},
        {"profile": "game-b", "display_name": "Game B", "game_type": "fmv_visual_novel"},
    ]
    assert db.list_source_revisions("transaction-game", "sheet-failure") == []
    assert db.list_source_sheets("transaction-game") == []
    assert db.list_story_scenes("transaction-game") == []


def test_source_can_claim_legacy_scene_only_when_stored_value_matches(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.save_story_project(
        "game-a", {
            "title": "Game A", "source_summary": {}, "required_locales": [],
            "conflicts": [], "patch_items": [],
            "scenes": {"scene-a": {
                "scene_id": "scene-a", "group": "Flow", "order": 0,
                "cues": [], "choices": [], "outgoing": [],
            }},
        },
    )
    db.sync_workbook_import(
        profile="game-a", display_name="Game A", game_type="fmv_visual_novel",
        source_id="matching-source", source_name="Workbook",
        source_url="https://example.test/matching", sheets=_sheets([["scene-a"]]),
        scenes=[{"scene_id": "scene-a", "group": "Flow", "source_row": 1}],
        links=[], cases=[], cues=[], choices=[],
    )
    provenance = db.list_source_entity_provenance("game-a", source_id="matching-source")
    assert len(provenance) == 1
    assert provenance[0]["entity_type"] == "scene"
    assert provenance[0]["status"] == "active"


def test_workbook_importer_syncs_revision_and_parsed_rows_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    db = QADatabase(root / "data" / "qa_profiles" / "qa_game-a.sqlite3")
    workbook = Workbook()
    flow = workbook.active
    flow.title = "FlowDemo"
    flow.append(["Flow", "Flow"])
    flow.append(["01_Scene_A", "01_Scene_B"])
    cases = workbook.create_sheet("Checklist")
    cases.append(["Scene Node", "Final Result"])
    cases.append(["01_Scene_A", "Pending"])
    localization = workbook.create_sheet("Luna Choice")
    localization.append(["Key", "---", "lang-en", "lang-th"])
    localization.append(["01_Scene_A_Choice1", "01_Scene_A", "Go Left", "ไปทางซ้าย"])
    alternate = workbook.create_sheet("ชีต10")
    alternate.append(["Key", "---", "lang-en", "lang-th"])
    alternate.append(["01_Scene_A_Choice1", "01_Scene_A", "Move Left", "เดินไปทางซ้าย"])
    payload = BytesIO()
    workbook.save(payload)
    workbook.close()
    monkeypatch.setattr(
        workbook_import,
        "_read_workbook_source",
        lambda _source: (BytesIO(payload.getvalue()), "QA fixture workbook"),
    )
    source_url = "https://docs.google.com/spreadsheets/d/sheet-fixture/edit"

    first = workbook_import.import_source_workbook(
        db,
        profile="game-a",
        game_name="Game A",
        game_type="fmv_visual_novel",
        source_url=source_url,
    )
    second = workbook_import.import_source_workbook(
        db,
        profile="game-a",
        game_name="Game A",
        game_type="fmv_visual_novel",
        source_url=source_url,
    )

    assert first["source_changed"] is True
    assert second["source_changed"] is False
    assert first["revision_hash"] == second["revision_hash"]
    assert second["flow_scenes_added"] == 0
    assert second["flow_links_added"] == 0
    assert len(db.list_source_revisions("game-a", "sheet-fixture")) == 1
    assert len(db.list_source_revision_rows("game-a", "sheet-fixture")) == 8
    assert len(db.list_story_scenes("game-a")) == 2
    assert len(db.list_testcase_sources("game-a")) == 1
    assert db.story_summary("game-a")["choices"] == 1
    assert first["localization_conflicts"] == 1
    candidates = db.list_source_localization_candidates("game-a", source_id="sheet-fixture")
    assert len(candidates) == 2
    assert all(candidate["has_conflict"] for candidate in candidates)
    assert {candidate["payload"]["source_row"] for candidate in candidates} == {2}
    provenance_by_type = {
        row["entity_type"]: row
        for row in db.list_source_entity_provenance("game-a", source_id="sheet-fixture")
    }
    assert provenance_by_type["scene"]["sheet_name"] == "FlowDemo"
    assert provenance_by_type["scene"]["row_number"] == 2
    assert provenance_by_type["link"]["row_number"] == 2
    assert provenance_by_type["testcase"]["sheet_name"] == "Checklist"
    assert provenance_by_type["testcase"]["row_number"] == 2
    assert provenance_by_type["choice"]["sheet_name"] == "Luna Choice"
    assert provenance_by_type["choice"]["row_number"] == 2

    from qa_framework import mcp_tools

    monkeypatch.setattr(
        QADatabase, "for_profile", classmethod(lambda cls, _profile: db)
    )
    revision_payload = mcp_tools.get_source_revision_tool("game-a", "sheet-fixture")
    assert revision_payload["revision_hash"] == first["revision_hash"]
    assert any(
        row["sheet_name"] == "Luna Choice" and row["row_number"] == 2
        for row in revision_payload["entities"]
    )
    assert len(revision_payload["localization_candidates"]) == 2


def test_checklist_import_skips_repeated_column_headers() -> None:
    rows = [
        ["# / ลำดับ", "ชื่อซีน (Scene Node)", "Final Result"],
        [1, "Scene_A", "Pending"],
        ["# / ลำดับ", "ชื่อซีน (Scene Node)", "Final Result"],
        [2, "Scene_B", "Fail"],
    ]

    cases = workbook_import._checklist_cases("Master Checklist", rows)

    assert [case["scene_id"] for case in cases] == ["Scene_A", "Scene_B"]
    assert [case["source_row"] for case in cases] == [2, 4]


def test_checklist_import_keeps_choice_variants_for_the_same_scene() -> None:
    rows = [
        ["Scene Node", "Choice Name", "Final Result"],
        ["Scene_25EndAYA009", "Don't Choose", "Pending"],
        ["Scene_25EndAYA009", "Don't Kill Sophia", "Pending"],
    ]

    cases = workbook_import._checklist_cases("Master Checklist", rows)

    assert len(cases) == 2
    assert len({case["case_id"] for case in cases}) == 2
    assert [case["source_row"] for case in cases] == [2, 3]


def test_workbook_revision_marks_removed_entities_stale_and_preserves_other_owner(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path)
    common = {
        "profile": "game-a",
        "display_name": "Game A",
        "game_type": "fmv_visual_novel",
        "source_name": "Workbook",
        "source_url": "https://example.test/workbook",
        "sheets": _sheets([["version 1"]]),
        "scenes": [{"scene_id": "shared-scene", "group": "Source A"}],
        "links": [],
        "cases": [{"case_id": "source-a-case", "scene_id": "shared-scene", "source_row": 2}],
        "cues": [{
            "scene_id": "shared-scene", "key": "a-cue", "start": 0, "end": 1,
            "translations": {"en": "Line A"}, "source_sheet": "Subtitles",
        }],
        "choices": [],
    }
    db.sync_workbook_import(source_id="source-a", **common)

    # Another source references the same scene key; it must not relabel or
    # claim the entity already owned by source A.
    other_source = {
        **common,
        "source_id": "source-b",
        "source_name": "Second workbook",
        "scenes": [{"scene_id": "shared-scene", "group": "Source B"}],
        "cases": [], "cues": [], "choices": [],
    }
    db.sync_workbook_import(**other_source)
    assert db.list_story_scenes("game-a")[0]["group_name"] == "Source A"
    assert db.list_source_entity_provenance("game-a", source_id="source-b") == []

    updated = {
        **common,
        "sheets": _sheets([["version 2"]]),
        "scenes": [{"scene_id": "shared-scene", "group": "Source A"}],
        "cases": [], "cues": [],
    }
    db.sync_workbook_import(source_id="source-a", **updated)
    stale = db.list_source_entity_provenance(
        "game-a", source_id="source-a", status="stale"
    )
    assert {row["entity_type"] for row in stale} >= {"testcase", "cue"}
    # Historical graph rows are retained; provenance says they are no longer
    # part of the latest source revision.
    assert len(db.list_testcase_sources("game-a")) == 0
    assert db.story_summary("game-a")["subtitles"] == 1
    current_project = db.load_story_project("game-a")
    assert current_project is not None
    assert current_project["scenes"]["shared-scene"]["cues"] == []
    with db._connect() as connection:  # noqa: SLF001 - historical source row is intentionally retained
        assert connection.execute(
            "SELECT COUNT(*) FROM test_cases WHERE profile = 'game-a'"
        ).fetchone()[0] == 1


def test_shared_database_profile_migration_preserves_source_citations(tmp_path: Path) -> None:
    shared = QADatabase(tmp_path / "shared.sqlite3")
    shared.register_game("game-a", "Game A", "fmv_visual_novel")
    shared.sync_workbook_import(
        profile="game-a", display_name="Game A", game_type="fmv_visual_novel",
        source_id="migration-sheet", source_name="Workbook",
        source_url="https://example.test/migration", sheets=_sheets([["Flow"], ["A"]]),
        scenes=[{"scene_id": "scene-a", "group": "Flow", "source_sheet": "Flow", "source_row": 2}],
        links=[], cases=[], cues=[], choices=[],
    )
    destination = QADatabase(tmp_path / "profile.sqlite3")

    destination._migrate_profile_from_shared(shared.path, "game-a")  # noqa: SLF001

    assert len(destination.list_source_revisions("game-a", "migration-sheet")) == 1
    assert destination.list_source_revision_rows("game-a", "migration-sheet")[1]["payload"] == ["A"]
    provenance = destination.list_source_entity_provenance("game-a", source_id="migration-sheet")
    assert provenance[0]["sheet_name"] == "Flow"
    assert provenance[0]["row_number"] == 2
