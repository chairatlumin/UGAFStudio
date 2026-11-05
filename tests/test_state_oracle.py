from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from qa_framework.gameplay_agent.state_oracle import ProfileStateOracle


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE subtitle_cues "
            "(profile TEXT, scene_id TEXT, translations_json TEXT)"
        )
        connection.execute(
            "CREATE TABLE story_choices "
            "(profile TEXT, scene_id TEXT, translations_json TEXT)"
        )
        connection.executemany(
            "INSERT INTO story_choices VALUES (?, ?, ?)",
            [
                ("hbs-demo", "scene-left", json.dumps({"en": "Go Left", "th": "ไปทางซ้าย"})),
                ("other-game", "other-scene", json.dumps({"en": "Go Left"})),
            ],
        )
        connection.execute(
            "INSERT INTO subtitle_cues VALUES (?, ?, ?)",
            ("hbs-demo", "scene-subtitle", json.dumps({"en": "The door is open", "th": "ประตูเปิดแล้ว"})),
        )


def test_recognizes_profile_choice_and_localized_subtitle(tmp_path: Path) -> None:
    path = tmp_path / "game.sqlite3"
    _database(path)
    oracle = ProfileStateOracle.from_database("hbs-demo", path)

    choice = oracle.recognize([{"text": "Go Left"}])
    assert choice["known"] is True
    assert choice["scene_ids"] == ["scene-left"]
    assert choice["matches"][0]["kind"] == "story_choice"

    subtitle = oracle.recognize([{"text": "ประตูเปิดแล้ว"}])
    assert subtitle["known"] is True
    assert subtitle["scene_ids"] == ["scene-subtitle"]


def test_unknown_and_other_profile_text_do_not_match(tmp_path: Path) -> None:
    path = tmp_path / "game.sqlite3"
    _database(path)
    oracle = ProfileStateOracle.from_database("hbs-demo", path)
    assert oracle.recognize([{"text": "unknown test screen"}])["known"] is False
    assert oracle.recognize([{"text": "Unrelated"}])["known"] is False


def test_profile_menu_cues_can_recognize_without_database(tmp_path: Path) -> None:
    oracle = ProfileStateOracle.from_database("hbs-demo", tmp_path / "missing.sqlite3", ["Main Menu"])
    match = oracle.recognize([{"text": "Main Menu"}])
    assert match["known"] is True
    assert match["matches"][0]["kind"] == "profile_menu"


def test_profile_menu_cue_matches_tesseract_merged_words(tmp_path: Path) -> None:
    oracle = ProfileStateOracle.from_database("hbs-demo", tmp_path / "missing.sqlite3", ["New Game"])
    assert oracle.recognize([{"text": "NEWGAME"}])["known"] is True
