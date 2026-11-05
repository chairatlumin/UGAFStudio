from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database.database import QADatabase
from app.qa.game_memory_vault import export_game_vault, search_game_memory


def _populated_db(tmp_path: Path, profile: str) -> QADatabase:
    db = QADatabase(tmp_path / f"{profile}.sqlite3")
    db.register_game(profile, profile, "fmv_visual_novel")
    db.sync_workbook_import(
        profile=profile,
        display_name=profile,
        game_type="fmv_visual_novel",
        source_id="sheet-id",
        source_name="QA workbook",
        source_url="https://example.test/workbook",
        sheets=[
            {
                "sheet_name": "Flow",
                "rows": [["Flow"], ["scene-01"], ["Go Left"], [None]],
                "row_count": 3, "column_count": 1, "hyperlinks": [],
            },
            {
                "sheet_name": "Choice",
                "rows": [["Key", "---", "lang-en"], [None, None, None],
                         [None, None, None], ["left", "scene-01", "Go Left"]],
                "row_count": 2, "column_count": 3, "hyperlinks": [],
            },
        ],
        scenes=[{
            "scene_id": "scene-01", "group": "Chapter 1",
            "source_sheet": "Flow", "source_row": 2,
        }],
        links=[],
        cases=[{
            "case_id": "case-01", "scene_id": "scene-01", "group": "Chapter 1",
            "source_sheet": "Checklist", "source_row": 7,
        }],
        cues=[],
        choices=[{
            "scene_id": "scene-01", "key": "left",
            "translations": {"en": "Go Left"}, "source_sheet": "Choice", "source_row": 4,
        }],
    )
    db.store_game_memory(
        profile, "choice.timeout_behavior", "user_requirement",
        "Timer picks the fifth option if the player waits.", source="User-provided QA requirement",
    )
    manifest_path = tmp_path / f"{profile}-run.json"
    manifest = {
        "profile": profile, "game": profile, "run_id": "run-01", "steam_build_id": "build-9",
        "status": "FINISHED", "qa_status": "NEEDS_REVIEW", "testcase_id": "case-01",
        "expected": ["Go Left"], "trace": "artifacts/trace.json",
        "session_report": "reports/run.html",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    db.record_run(manifest, manifest_path)
    db.record_feedback(
        "defect-01", "localization", "Thai text is clipped in the choice menu.",
        run_id="run-01", case_id="case-01",
    )
    return db


def _markdown_snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*.md")
    }


def test_vault_export_is_stable_and_rebuildable(tmp_path: Path) -> None:
    db = _populated_db(tmp_path, "game-a")
    vault = tmp_path / "vault"
    first = export_game_vault(db, "game-a", vault)
    snapshot = _markdown_snapshot(vault)
    second = export_game_vault(db, "game-a", vault)

    assert first["markdown_pages"] >= 7
    assert first["search_documents"] > 0
    assert second["markdown_pages"] == first["markdown_pages"]
    assert _markdown_snapshot(vault) == snapshot
    assert "[[" in snapshot["Home.md"]
    assert any(path.startswith("Requirements/") for path in snapshot)
    assert any(path.startswith("Sources/") and "Go Left" in content for path, content in snapshot.items())
    assert any(path.startswith("Scenes/") and "Choice" in content and "!4" in content for path, content in snapshot.items())
    assert any(path.startswith("Testcases/") and "Checklist!7" in content for path, content in snapshot.items())
    assert any(path.startswith("Runs/") and "case-01" in content for path, content in snapshot.items())
    assert any(path.startswith("Defects/") and "Thai text is clipped" in content for path, content in snapshot.items())

    for markdown in vault.rglob("*.md"):
        markdown.unlink()
    export_game_vault(db, "game-a", vault)
    assert _markdown_snapshot(vault) == snapshot

    personal_note = vault / "Personal Notes.md"
    personal_note.write_text("not managed by UGAF", encoding="utf-8")
    requirement = next(vault.glob("Requirements/*.md"))
    with db._connect() as connection:  # noqa: SLF001 - fixture mutation for rebuild behavior
        connection.execute(
            "DELETE FROM game_memory WHERE profile = ? AND memory_key = ?",
            ("game-a", "choice.timeout_behavior"),
        )
    export_game_vault(db, "game-a", vault)
    assert personal_note.read_text(encoding="utf-8") == "not managed by UGAF"
    assert not requirement.exists()


def test_search_returns_citations_and_never_crosses_game_profiles(tmp_path: Path) -> None:
    first = _populated_db(tmp_path, "game-a")
    second = _populated_db(tmp_path, "game-b")

    results = search_game_memory(first, "game-a", "Go Left", limit=10)
    assert results
    assert {item["profile"] for item in results} == {"game-a"}
    assert all(item["title"] and item["entity_id"] for item in results)
    assert any(
        item["citation"].get("sheet") == "Flow" and item["citation"].get("row") == 3
        for item in results
    )
    with first._connect() as connection:  # noqa: SLF001 - derived index assertions
        assert connection.execute(
            "SELECT COUNT(*) FROM game_memory_fts WHERE profile = ? AND entity_type = 'source_row'",
            ("game-a",),
        ).fetchone()[0] == 5
    assert search_game_memory(second, "game-b", "timer fifth", limit=10)
    assert search_game_memory(first, "game-a", "Thai clipped", limit=10)
    assert search_game_memory(first, "game-a", "*", limit=10) == []


def test_mcp_memory_search_and_vault_export_wrappers_are_profile_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qa_framework import mcp_tools

    db = _populated_db(tmp_path, "game-a")
    monkeypatch.setattr(QADatabase, "for_profile", classmethod(lambda cls, _profile: db))

    search = mcp_tools.search_game_memory_tool("game-a", "Go Left")
    export = mcp_tools.export_game_vault_tool("game-a", str(tmp_path / "mcp-vault"))

    assert search["profile"] == "game-a"
    assert search["count"] > 0
    assert export["profile"] == "game-a"
    assert (Path(export["vault_path"]) / "Home.md").is_file()
