from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _writable_base() -> Path:
    """Mutable DB beside the exe when frozen, else repo root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return ROOT


def _resource_base() -> Path:
    """Read-only bundled data (PyInstaller temp dir when frozen, else repo)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return ROOT


DEFAULT_DATABASE = _writable_base() / "data" / "ugaf_qa.sqlite3"
PROFILE_DB_DIR = _writable_base() / "data" / "qa_profiles"


def sanitize_profile_key(profile: str) -> str:
    """Filesystem-safe per-game key; never touches the shared DB."""
    key = (profile or "").strip().casefold().replace(" ", "-")
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in key).strip("-_")
    return safe or "unknown"


def profile_database_path(profile: str) -> Path:
    return PROFILE_DB_DIR / f"qa_{sanitize_profile_key(profile)}.sqlite3"


class QADatabase:
    """Local SQLite store for game flow, source cases, runs, and QA findings."""

    def __init__(self, path: Path = DEFAULT_DATABASE) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def for_profile(cls, profile: str) -> QADatabase:
        """Per-game SQLite file; migrates only this profile's rows from shared DB."""
        # Copy only this game's existing rows; keep the shared database intact.
        path = profile_database_path(profile)
        db = cls(path)
        shared = DEFAULT_DATABASE
        if (
            profile
            and shared.is_file()
            and path.resolve() != shared.resolve()
            and db.story_summary(profile)["testcases"] == 0
            and not db.list_runs(profile=profile, limit=1)
        ):
            db._migrate_profile_from_shared(shared, profile)
        return db

    def _migrate_profile_from_shared(self, shared: Path, profile: str) -> None:
        try:
            src = sqlite3.connect(shared, timeout=10)
            src.row_factory = sqlite3.Row
            with self._connect() as dst:
                for table, where in (
                    ("games", "profile = ?"),
                    ("story_projects", "profile = ?"),
                    ("patch_items", "profile = ?"),
                    ("story_scenes", "profile = ?"),
                    ("subtitle_cues", "profile = ?"),
                    ("story_choices", "profile = ?"),
                    ("story_links", "profile = ?"),
                    ("test_cases", "profile = ?"),
                    ("qa_runs", "profile = ?"),
                    ("qa_campaigns", "profile = ?"),
                    ("story_evidence", "profile = ?"),
                    ("source_sheets", "profile = ?"),
                    ("source_revisions", "profile = ?"),
                    ("source_revision_rows", "profile = ?"),
                    ("source_entity_provenance", "profile = ?"),
                    ("source_localization_candidates", "profile = ?"),
                    ("game_memory", "profile = ?"),
                    ("unreal_telemetry_events", "profile = ?"),
                    # FTS rows are derived and are rebuilt from canonical profile data on use.
                ):
                    try:
                        cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
                        if not cols:
                            continue
                        placeholders = ", ".join("?" for _ in cols)
                        rows = src.execute(
                            f"SELECT {', '.join(cols)} FROM {table} WHERE {where}", (profile,)
                        ).fetchall()
                        dst.executemany(
                            f"INSERT OR IGNORE INTO {table}({', '.join(cols)})"
                            f" VALUES ({placeholders})",
                            [tuple(r) for r in rows],
                        )
                    except sqlite3.Error:
                        continue
                try:
                    campaign_ids = [
                        row[0]
                        for row in src.execute(
                            "SELECT campaign_id FROM qa_campaigns WHERE profile = ?",
                            (profile,),
                        )
                    ]
                    if campaign_ids:
                        placeholders = ", ".join("?" for _ in campaign_ids)
                        cols = [r[1] for r in src.execute("PRAGMA table_info(qa_campaign_attempts)")]
                        if cols:
                            rows = src.execute(
                                f"SELECT {', '.join(cols)} FROM qa_campaign_attempts "
                                f"WHERE campaign_id IN ({placeholders})",
                                campaign_ids,
                            ).fetchall()
                            dst.executemany(
                                f"INSERT OR IGNORE INTO qa_campaign_attempts({', '.join(cols)}) "
                                f"VALUES ({', '.join('?' for _ in cols)})",
                                [tuple(row) for row in rows],
                            )
                except sqlite3.Error:
                    pass
                try:
                    run_ids = [
                        r[0]
                        for r in src.execute(
                            "SELECT run_id FROM qa_runs WHERE profile = ?", (profile,)
                        )
                    ]
                    if run_ids:
                        q = ", ".join("?" for _ in run_ids)
                        for table in ("testcase_results", "qa_feedback"):
                            cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
                            if not cols:
                                continue
                            rows = src.execute(
                                f"SELECT {', '.join(cols)} FROM {table} WHERE run_id IN ({q})",
                                run_ids,
                            ).fetchall()
                            dst.executemany(
                                f"INSERT OR IGNORE INTO {table}({', '.join(cols)})"
                                f" VALUES ({', '.join('?' for _ in cols)})",
                                [tuple(row) for row in rows],
                            )
                except sqlite3.Error:
                    pass
            src.close()
        except sqlite3.Error:
            pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS games (
                    profile TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    game_type TEXT NOT NULL,
                    steam_app_id TEXT NOT NULL DEFAULT '',
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS story_projects (
                    profile TEXT PRIMARY KEY REFERENCES games(profile) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    source_summary_json TEXT NOT NULL,
                    required_locales_json TEXT NOT NULL,
                    conflicts_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS patch_items (
                    profile TEXT NOT NULL REFERENCES story_projects(profile) ON DELETE CASCADE,
                    item_order INTEGER NOT NULL,
                    version TEXT NOT NULL,
                    build_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    text TEXT NOT NULL,
                    scene_ids_json TEXT NOT NULL,
                    PRIMARY KEY (profile, item_order)
                );
                CREATE TABLE IF NOT EXISTS story_scenes (
                    profile TEXT NOT NULL REFERENCES story_projects(profile) ON DELETE CASCADE,
                    scene_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    scene_order INTEGER NOT NULL,
                    cases_json TEXT NOT NULL,
                    PRIMARY KEY (profile, scene_id)
                );
                CREATE TABLE IF NOT EXISTS subtitle_cues (
                    profile TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    cue_key TEXT NOT NULL,
                    start_seconds REAL NOT NULL,
                    end_seconds REAL NOT NULL,
                    translations_json TEXT NOT NULL,
                    source_sheet TEXT NOT NULL,
                    PRIMARY KEY (profile, scene_id, cue_key, start_seconds, end_seconds),
                    FOREIGN KEY (profile, scene_id) REFERENCES story_scenes(profile, scene_id)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS story_choices (
                    profile TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    choice_key TEXT NOT NULL,
                    translations_json TEXT NOT NULL,
                    source_sheet TEXT NOT NULL,
                    PRIMARY KEY (profile, scene_id, choice_key),
                    FOREIGN KEY (profile, scene_id) REFERENCES story_scenes(profile, scene_id)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS story_links (
                    profile TEXT NOT NULL,
                    source_scene TEXT NOT NULL,
                    target_scene TEXT NOT NULL,
                    choice_key TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (profile, source_scene, target_scene, choice_key),
                    FOREIGN KEY (profile, source_scene)
                        REFERENCES story_scenes(profile, scene_id) ON DELETE CASCADE,
                    FOREIGN KEY (profile, target_scene)
                        REFERENCES story_scenes(profile, scene_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS test_cases (
                    profile TEXT NOT NULL REFERENCES games(profile) ON DELETE CASCADE,
                    case_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL DEFAULT '',
                    source_row INTEGER,
                    group_name TEXT NOT NULL DEFAULT '',
                    source_status TEXT NOT NULL DEFAULT '',
                    feedback_tags_json TEXT NOT NULL DEFAULT '[]',
                    source_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (profile, case_id)
                );
                CREATE TABLE IF NOT EXISTS qa_runs (
                    run_id TEXT PRIMARY KEY,
                    profile TEXT NOT NULL REFERENCES games(profile),
                    build_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    qa_status TEXT NOT NULL DEFAULT 'UNASSERTED',
                    started_at_utc TEXT NOT NULL,
                    finished_at_utc TEXT,
                    manifest_path TEXT NOT NULL,
                    trace_path TEXT NOT NULL DEFAULT '',
                    report_path TEXT NOT NULL DEFAULT '',
                    manifest_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qa_campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    profile TEXT NOT NULL REFERENCES games(profile) ON DELETE CASCADE,
                    idempotency_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    qa_status TEXT NOT NULL DEFAULT 'UNASSERTED',
                    selected_case_ids_json TEXT NOT NULL DEFAULT '[]',
                    selected_categories_json TEXT NOT NULL DEFAULT '[]',
                    run_ids_json TEXT NOT NULL DEFAULT '[]',
                    started_at_utc TEXT NOT NULL,
                    finished_at_utc TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_qa_campaign_idempotency
                    ON qa_campaigns(profile, idempotency_key) WHERE idempotency_key <> '';
                CREATE INDEX IF NOT EXISTS idx_qa_campaign_profile_time
                    ON qa_campaigns(profile, started_at_utc DESC);
                CREATE TABLE IF NOT EXISTS qa_campaign_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL REFERENCES qa_campaigns(campaign_id) ON DELETE CASCADE,
                    retry_key TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    qa_status TEXT NOT NULL DEFAULT 'UNASSERTED',
                    run_id TEXT NOT NULL DEFAULT '',
                    started_at_utc TEXT NOT NULL,
                    finished_at_utc TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(campaign_id, retry_key),
                    UNIQUE(campaign_id, attempt_number)
                );
                CREATE INDEX IF NOT EXISTS idx_qa_campaign_attempts_time
                    ON qa_campaign_attempts(campaign_id, attempt_number);
                CREATE TABLE IF NOT EXISTS testcase_results (
                    run_id TEXT NOT NULL REFERENCES qa_runs(run_id) ON DELETE CASCADE,
                    case_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expected_json TEXT NOT NULL DEFAULT '[]',
                    observed TEXT NOT NULL DEFAULT '',
                    assertions_json TEXT NOT NULL DEFAULT '[]',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (run_id, case_id)
                );
                CREATE TABLE IF NOT EXISTS qa_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    case_id TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES qa_runs(run_id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS story_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    profile TEXT NOT NULL REFERENCES games(profile) ON DELETE CASCADE,
                    scene_id TEXT NOT NULL DEFAULT '',
                    evidence_type TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_story_evidence_profile
                    ON story_evidence(profile, created_at_utc DESC);
                CREATE TABLE IF NOT EXISTS source_sheets (
                    profile TEXT NOT NULL REFERENCES games(profile) ON DELETE CASCADE,
                    source_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    rows_json TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    column_count INTEGER NOT NULL,
                    hyperlinks_json TEXT NOT NULL DEFAULT '[]',
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (profile, source_id, sheet_name)
                );
                CREATE TABLE IF NOT EXISTS game_memory (
                    profile TEXT NOT NULL REFERENCES games(profile) ON DELETE CASCADE,
                    memory_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (profile, memory_key)
                );
                CREATE TABLE IF NOT EXISTS source_revisions (
                    profile TEXT NOT NULL REFERENCES games(profile) ON DELETE CASCADE,
                    source_id TEXT NOT NULL,
                    revision_hash TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    imported_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('current', 'superseded')),
                    PRIMARY KEY (profile, source_id, revision_hash)
                );
                CREATE TABLE IF NOT EXISTS source_revision_rows (
                    profile TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    revision_hash TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    row_number INTEGER NOT NULL,
                    row_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (profile, source_id, revision_hash, sheet_name, row_number),
                    FOREIGN KEY (profile, source_id, revision_hash)
                        REFERENCES source_revisions(profile, source_id, revision_hash)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS source_entity_provenance (
                    profile TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    sheet_name TEXT NOT NULL DEFAULT '',
                    row_number INTEGER,
                    revision_hash TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active', 'stale')),
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (profile, source_id, entity_type, entity_key),
                    FOREIGN KEY (profile, source_id, revision_hash)
                        REFERENCES source_revisions(profile, source_id, revision_hash)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS source_localization_candidates (
                    profile TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    revision_hash TEXT NOT NULL,
                    entity_type TEXT NOT NULL CHECK(entity_type IN ('cue', 'choice')),
                    entity_key TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    row_number INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (profile, source_id, revision_hash, entity_type,
                                 entity_key, sheet_name, row_number),
                    FOREIGN KEY (profile, source_id, revision_hash)
                        REFERENCES source_revisions(profile, source_id, revision_hash)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS unreal_telemetry_events (
                    profile TEXT NOT NULL REFERENCES games(profile) ON DELETE CASCADE,
                    session_id TEXT NOT NULL,
                    build_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    emitted_at_utc TEXT NOT NULL,
                    received_at_utc TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (profile, session_id, event_id),
                    UNIQUE (profile, session_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_unreal_events_session
                    ON unreal_telemetry_events(profile, session_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_source_revisions_current
                    ON source_revisions(profile, source_id, status);
                CREATE INDEX IF NOT EXISTS idx_source_entities_state
                    ON source_entity_provenance(profile, entity_type, entity_key, status);
                CREATE VIRTUAL TABLE IF NOT EXISTS game_memory_fts USING fts5(
                    profile UNINDEXED, entity_type UNINDEXED, entity_id UNINDEXED,
                    title, body, citation, tokenize='unicode61 remove_diacritics 2'
                );
                CREATE INDEX IF NOT EXISTS idx_story_scenes_order
                    ON story_scenes(profile, scene_order);
                CREATE INDEX IF NOT EXISTS idx_qa_runs_profile_date
                    ON qa_runs(profile, started_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_testcase_results_case
                    ON testcase_results(case_id, status);
                """
            )

    def register_game(
        self,
        profile: str,
        display_name: str,
        game_type: str,
        steam_app_id: str = "",
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO games(profile, display_name, game_type, steam_app_id, updated_at_utc)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(profile) DO UPDATE SET display_name=excluded.display_name,
                   game_type=excluded.game_type, steam_app_id=excluded.steam_app_id,
                   updated_at_utc=excluded.updated_at_utc""",
                (profile, display_name, game_type, steam_app_id, now),
            )

    def list_games(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT profile, display_name, game_type FROM games ORDER BY display_name"
                )
            ]

    def save_story_evidence(
        self,
        profile: str,
        scene_id: str,
        evidence_type: str,
        image_path: str,
        result: dict[str, Any],
    ) -> str:
        import uuid

        evidence_id = uuid.uuid4().hex
        with self._connect() as connection:
            if scene_id.strip():
                game = connection.execute(
                    "SELECT display_name FROM games WHERE profile = ?", (profile,)
                ).fetchone()
                if game is None:
                    raise ValueError(f"Unknown game profile: {profile}")
                now = datetime.now(UTC).isoformat()
                connection.execute(
                    """INSERT OR IGNORE INTO story_projects(profile, title, source_summary_json,
                       required_locales_json, conflicts_json, updated_at_utc)
                       VALUES (?, ?, '{}', '[]', '[]', ?)""",
                    (profile, str(game["display_name"]), now),
                )
                order = int(connection.execute(
                    "SELECT COUNT(*) FROM story_scenes WHERE profile = ?", (profile,)
                ).fetchone()[0])
                connection.execute(
                    """INSERT OR IGNORE INTO story_scenes(profile, scene_id, group_name,
                       scene_order, cases_json) VALUES (?, ?, 'Image evidence', ?, '[]')""",
                    (profile, scene_id.strip(), order),
                )
            connection.execute(
                """INSERT INTO story_evidence(evidence_id, profile, scene_id, evidence_type,
                   image_path, result_json, created_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    evidence_id,
                    profile,
                    scene_id,
                    evidence_type,
                    image_path,
                    _json(result),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return evidence_id

    def list_story_scenes(self, profile: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT scene_id, group_name, scene_order FROM story_scenes "
                    "WHERE profile = ? ORDER BY scene_order, scene_id",
                    (profile,),
                )
            ]

    def upsert_story_scenes(self, profile: str, scenes: list[dict[str, Any]]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """INSERT INTO story_scenes(profile, scene_id, group_name, scene_order, cases_json)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(profile, scene_id) DO UPDATE SET group_name=excluded.group_name,
                   scene_order=excluded.scene_order, cases_json=excluded.cases_json""",
                [
                    (
                        profile, str(scene["scene_id"]), str(scene.get("group", "Imported Flow")),
                        int(scene.get("order", index)), _json(scene.get("cases", [])),
                    )
                    for index, scene in enumerate(scenes)
                ],
            )

    def upsert_story_links(self, profile: str, links: list[dict[str, str]]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """INSERT OR IGNORE INTO story_links(profile, source_scene, target_scene, choice_key)
                   VALUES (?, ?, ?, ?)""",
                [
                    (
                        profile, str(link["source"]), str(link["target"]),
                        str(link.get("choice_key", "")),
                    )
                    for link in links
                ],
            )

    def upsert_story_localization(
        self, profile: str, cues: list[dict[str, Any]], choices: list[dict[str, Any]]
    ) -> None:
        with self._connect() as connection:
            for entry in cues:
                scene_id = str(entry["scene_id"])
                connection.execute(
                    """INSERT OR IGNORE INTO story_scenes(profile, scene_id, group_name,
                       scene_order, cases_json) VALUES (?, ?, 'Localization',
                       (SELECT COUNT(*) FROM story_scenes WHERE profile = ?), '[]')""",
                    (profile, scene_id, profile),
                )
                connection.execute(
                    """INSERT INTO subtitle_cues(profile, scene_id, cue_key, start_seconds,
                       end_seconds, translations_json, source_sheet) VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(profile, scene_id, cue_key, start_seconds, end_seconds)
                       DO UPDATE SET translations_json=excluded.translations_json,
                       source_sheet=excluded.source_sheet""",
                    (
                        profile, scene_id, str(entry["key"]), float(entry["start"]),
                        float(entry["end"]), _json(entry.get("translations", {})),
                        str(entry.get("source_sheet", "")),
                    ),
                )
            for entry in choices:
                scene_id = str(entry["scene_id"])
                connection.execute(
                    """INSERT OR IGNORE INTO story_scenes(profile, scene_id, group_name,
                       scene_order, cases_json) VALUES (?, ?, 'Localization',
                       (SELECT COUNT(*) FROM story_scenes WHERE profile = ?), '[]')""",
                    (profile, scene_id, profile),
                )
                connection.execute(
                    """INSERT INTO story_choices(profile, scene_id, choice_key,
                       translations_json, source_sheet) VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(profile, scene_id, choice_key)
                       DO UPDATE SET translations_json=excluded.translations_json,
                       source_sheet=excluded.source_sheet""",
                    (
                        profile, scene_id, str(entry["key"]),
                        _json(entry.get("translations", {})), str(entry.get("source_sheet", "")),
                    ),
                )

    def save_source_sheets(
        self, profile: str, source_id: str, source_name: str,
        sheets: list[dict[str, Any]], source_url: str = "",
    ) -> int:
        self.sync_source_snapshot(
            profile, source_id, source_name, sheets, source_url=source_url
        )
        return len(sheets)

    def sync_source_snapshot(
        self,
        profile: str,
        source_id: str,
        source_name: str,
        sheets: list[dict[str, Any]],
        *,
        source_url: str = "",
    ) -> dict[str, Any]:
        """Atomically store a current source snapshot and immutable row revisions."""
        import hashlib

        normalized_sheets = [
            {
                "sheet_name": str(sheet["sheet_name"]),
                "rows": sheet.get("rows", []),
                "row_count": int(sheet.get("row_count", 0)),
                "column_count": int(sheet.get("column_count", 0)),
                "hyperlinks": sheet.get("hyperlinks", []),
            }
            for sheet in sheets
        ]
        canonical = _json({"source_url": source_url, "sheets": normalized_sheets})
        revision_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        now = datetime.now(UTC).isoformat()

        with self._connect() as connection:
            previous = connection.execute(
                "SELECT revision_hash FROM source_revisions "
                "WHERE profile = ? AND source_id = ? AND status = 'current'",
                (profile, source_id),
            ).fetchone()
            previous_hash = str(previous["revision_hash"]) if previous else None
            connection.execute(
                "UPDATE source_revisions SET status = 'superseded' "
                "WHERE profile = ? AND source_id = ? AND status = 'current'",
                (profile, source_id),
            )
            connection.execute(
                """INSERT INTO source_revisions(profile, source_id, revision_hash, source_url,
                   imported_at_utc, status) VALUES (?, ?, ?, ?, ?, 'current')
                   ON CONFLICT(profile, source_id, revision_hash) DO UPDATE SET
                   source_url=excluded.source_url, status='current'""",
                (profile, source_id, revision_hash, source_url, now),
            )
            connection.execute(
                "DELETE FROM source_sheets WHERE profile = ? AND source_id = ?",
                (profile, source_id),
            )
            for sheet in normalized_sheets:
                connection.execute(
                    """INSERT INTO source_sheets(profile, source_id, source_name, sheet_name,
                       rows_json, row_count, column_count, hyperlinks_json, updated_at_utc)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        profile, source_id, source_name, sheet["sheet_name"],
                        _json(sheet["rows"]), sheet["row_count"], sheet["column_count"],
                        _json(sheet["hyperlinks"]), now,
                    ),
                )
                for row_number, row in enumerate(sheet["rows"], start=1):
                    row_json = _json(row)
                    row_hash = hashlib.sha256(row_json.encode("utf-8")).hexdigest()
                    connection.execute(
                        """INSERT OR IGNORE INTO source_revision_rows(profile, source_id,
                           revision_hash, sheet_name, row_number, row_hash, payload_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            profile, source_id, revision_hash, sheet["sheet_name"],
                            row_number, row_hash, row_json,
                        ),
                    )

        return {
            "source_id": source_id,
            "revision_hash": revision_hash,
            "previous_revision_hash": previous_hash,
            "changed": previous_hash != revision_hash,
            "row_count": sum(len(sheet["rows"]) for sheet in normalized_sheets),
            "sheet_count": len(normalized_sheets),
        }

    def sync_workbook_import(
        self,
        *,
        profile: str,
        display_name: str,
        game_type: str,
        source_id: str,
        source_name: str,
        source_url: str,
        sheets: list[dict[str, Any]],
        scenes: list[dict[str, Any]],
        links: list[dict[str, str]],
        cases: list[dict[str, Any]],
        cues: list[dict[str, Any]],
        choices: list[dict[str, Any]],
        localization_candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Atomically sync raw workbook revision and its parsed graph entities."""
        import hashlib

        normalized_sheets = [
            {
                "sheet_name": str(sheet["sheet_name"]),
                "rows": sheet.get("rows", []),
                "row_count": int(sheet.get("row_count", 0)),
                "column_count": int(sheet.get("column_count", 0)),
                "hyperlinks": sheet.get("hyperlinks", []),
            }
            for sheet in sheets
        ]
        canonical = _json({"source_url": source_url, "sheets": normalized_sheets})
        revision_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        now = datetime.now(UTC).isoformat()
        scene_count = 0
        link_count = 0
        testcase_count = 0
        cue_count = 0
        choice_count = 0

        with self._connect() as connection:
            connection.execute(
                """INSERT INTO games(profile, display_name, game_type, steam_app_id, updated_at_utc)
                   VALUES (?, ?, ?, '', ?) ON CONFLICT(profile) DO UPDATE SET
                   display_name=excluded.display_name, game_type=excluded.game_type,
                   updated_at_utc=excluded.updated_at_utc""",
                (profile, display_name, game_type, now),
            )
            connection.execute(
                """INSERT OR IGNORE INTO story_projects(profile, title, source_summary_json,
                   required_locales_json, conflicts_json, updated_at_utc)
                   VALUES (?, ?, '{}', '[\"th\",\"en\"]', '[]', ?)""",
                (profile, display_name, now),
            )
            previous = connection.execute(
                "SELECT revision_hash FROM source_revisions WHERE profile = ? AND source_id = ? "
                "AND status = 'current'",
                (profile, source_id),
            ).fetchone()
            previous_hash = str(previous["revision_hash"]) if previous else None
            connection.execute(
                "UPDATE source_revisions SET status = 'superseded' "
                "WHERE profile = ? AND source_id = ? AND status = 'current'",
                (profile, source_id),
            )
            connection.execute(
                """INSERT INTO source_revisions(profile, source_id, revision_hash, source_url,
                   imported_at_utc, status) VALUES (?, ?, ?, ?, ?, 'current')
                   ON CONFLICT(profile, source_id, revision_hash) DO UPDATE SET
                   source_url=excluded.source_url, status='current'""",
                (profile, source_id, revision_hash, source_url, now),
            )
            connection.execute(
                "DELETE FROM source_sheets WHERE profile = ? AND source_id = ?",
                (profile, source_id),
            )
            for sheet in normalized_sheets:
                connection.execute(
                    """INSERT INTO source_sheets(profile, source_id, source_name, sheet_name,
                       rows_json, row_count, column_count, hyperlinks_json, updated_at_utc)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        profile, source_id, source_name, sheet["sheet_name"],
                        _json(sheet["rows"]), sheet["row_count"], sheet["column_count"],
                        _json(sheet["hyperlinks"]), now,
                    ),
                )
                for row_number, row in enumerate(sheet["rows"], start=1):
                    row_json = _json(row)
                    row_hash = hashlib.sha256(row_json.encode("utf-8")).hexdigest()
                    connection.execute(
                        """INSERT OR IGNORE INTO source_revision_rows(profile, source_id,
                           revision_hash, sheet_name, row_number, row_hash, payload_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (profile, source_id, revision_hash, sheet["sheet_name"], row_number, row_hash, row_json),
                    )

            for candidate in localization_candidates or []:
                entity_type = str(candidate.get("entity_type", ""))
                if entity_type not in {"cue", "choice"}:
                    continue
                if entity_type == "cue":
                    entity_key = _json([
                        candidate.get("scene_id", ""), candidate.get("key", ""),
                        float(candidate.get("start", 0)), float(candidate.get("end", 0)),
                    ])
                else:
                    entity_key = _json([
                        candidate.get("scene_id", ""), candidate.get("key", "")
                    ])
                connection.execute(
                    """INSERT OR IGNORE INTO source_localization_candidates(
                       profile, source_id, revision_hash, entity_type, entity_key,
                       sheet_name, row_number, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        profile, source_id, revision_hash, entity_type, entity_key,
                        str(candidate.get("source_sheet", "")),
                        int(candidate.get("source_row", 0)), _json(candidate),
                    ),
                )
            connection.execute(
                "UPDATE source_entity_provenance SET status = 'stale', updated_at_utc = ? "
                "WHERE profile = ? AND source_id = ? AND status = 'active'",
                (now, profile, source_id),
            )

            def entity_is_owned_by_source(entity_type: str, entity_key: str) -> bool:
                return connection.execute(
                    "SELECT 1 FROM source_entity_provenance WHERE profile = ? "
                    "AND source_id = ? AND entity_type = ? AND entity_key = ? LIMIT 1",
                    (profile, source_id, entity_type, entity_key),
                ).fetchone() is not None

            def record_entity(
                entity_type: str,
                entity_key: str,
                sheet_name: str = "",
                row_number: int | None = None,
            ) -> None:
                connection.execute(
                    """INSERT INTO source_entity_provenance(profile, source_id, entity_type,
                       entity_key, sheet_name, row_number, revision_hash, status, updated_at_utc)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
                       ON CONFLICT(profile, source_id, entity_type, entity_key) DO UPDATE SET
                       sheet_name=excluded.sheet_name, row_number=excluded.row_number,
                       revision_hash=excluded.revision_hash, status='active',
                       updated_at_utc=excluded.updated_at_utc""",
                    (
                        profile, source_id, entity_type, entity_key, sheet_name,
                        row_number, revision_hash, now,
                    ),
                )

            for scene in scenes:
                scene_id = str(scene.get("scene_id", "")).strip()
                if not scene_id:
                    continue
                entity_key = scene_id
                owned = entity_is_owned_by_source("scene", entity_key)
                existing_scene = connection.execute(
                    "SELECT group_name FROM story_scenes WHERE profile = ? AND scene_id = ?",
                    (profile, scene_id),
                ).fetchone()
                exists = existing_scene is not None
                matches_source = bool(
                    exists and str(existing_scene["group_name"])
                    == str(scene.get("group", "Imported Flow"))
                )
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO story_scenes(profile, scene_id, group_name,
                       scene_order, cases_json) VALUES (?, ?, ?, ?, '[]')""",
                    (
                        profile, scene_id, str(scene.get("group", "Imported Flow")),
                        int(scene.get("order", connection.execute(
                            "SELECT COUNT(*) FROM story_scenes WHERE profile = ?", (profile,)
                        ).fetchone()[0])),
                    ),
                )
                scene_count += cursor.rowcount
                if not exists or owned or matches_source:
                    record_entity(
                        "scene", entity_key, str(scene.get("source_sheet", scene.get("group", ""))),
                        scene.get("source_row"),
                    )

            for link in links:
                source = str(link.get("source", ""))
                target = str(link.get("target", ""))
                if not source or not target:
                    continue
                entity_key = _json([source, target, str(link.get("choice_key", ""))])
                owned = entity_is_owned_by_source("link", entity_key)
                exists = connection.execute(
                    """SELECT 1 FROM story_links WHERE profile = ? AND source_scene = ?
                       AND target_scene = ? AND choice_key = ?""",
                    (profile, source, target, str(link.get("choice_key", ""))),
                ).fetchone() is not None
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO story_links(profile, source_scene, target_scene, choice_key)
                       SELECT ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM story_scenes WHERE profile = ? AND scene_id = ?)
                         AND EXISTS (SELECT 1 FROM story_scenes WHERE profile = ? AND scene_id = ?)""",
                    (
                        profile, source, target, str(link.get("choice_key", "")),
                        profile, source, profile, target,
                    ),
                )
                link_count += cursor.rowcount
                # Link identity fully describes its stored value, so an exact
                # pre-existing link is safe to attribute to this source too.
                record_entity(
                    "link", entity_key, str(link.get("source_sheet", "")),
                    link.get("source_row"),
                )

            for case in cases:
                case_id = str(case.get("case_id", case.get("id", ""))).strip()
                if not case_id:
                    continue
                owned = entity_is_owned_by_source("testcase", case_id)
                existing_case = connection.execute(
                    "SELECT scene_id, source_row, group_name, source_status, source_json "
                    "FROM test_cases WHERE profile = ? AND case_id = ?",
                    (profile, case_id),
                ).fetchone()
                exists = existing_case is not None
                matches_source = bool(
                    exists
                    and str(existing_case["scene_id"]) == str(case.get("scene_id", ""))
                    and existing_case["source_row"] == case.get("source_row")
                    and str(existing_case["group_name"]) == str(case.get("group", ""))
                    and str(existing_case["source_status"])
                    == str(case.get("final_result", case.get("status", "")))
                    and _json(json.loads(existing_case["source_json"])) == _json(case)
                )
                if exists and not owned and not matches_source:
                    # An existing unowned case may be manual or from an older
                    # importer. Preserve it; do not silently claim/overwrite it.
                    continue
                connection.execute(
                    """INSERT INTO test_cases(profile, case_id, scene_id, source_row, group_name,
                       source_status, feedback_tags_json, source_json, updated_at_utc)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(profile, case_id) DO UPDATE SET scene_id=excluded.scene_id,
                       source_row=excluded.source_row, group_name=excluded.group_name,
                       source_status=excluded.source_status, feedback_tags_json=excluded.feedback_tags_json,
                       source_json=excluded.source_json, updated_at_utc=excluded.updated_at_utc""",
                    (
                        profile, case_id, str(case.get("scene_id", "")), case.get("source_row"),
                        str(case.get("group", "")), str(case.get("final_result", case.get("status", ""))),
                        _json(case.get("feedback_tags", [])), _json(case), now,
                    ),
                )
                record_entity(
                    "testcase", case_id, str(case.get("source_sheet", "")),
                    case.get("source_row"),
                )
                testcase_count += 1

            for table, entries, key_name in (
                ("subtitle_cues", cues, "key"), ("story_choices", choices, "key")
            ):
                for entry in entries:
                    scene_id = str(entry["scene_id"])
                    is_cue = table == "subtitle_cues"
                    entity_type = "cue" if is_cue else "choice"
                    if is_cue:
                        entity_key = _json([
                            scene_id, str(entry[key_name]),
                            float(entry.get("start", 0)), float(entry.get("end", 0)),
                        ])
                        existing_entry = connection.execute(
                            """SELECT translations_json, source_sheet FROM subtitle_cues
                               WHERE profile = ? AND scene_id = ?
                               AND cue_key = ? AND start_seconds = ? AND end_seconds = ?""",
                            (
                                profile, scene_id, str(entry[key_name]),
                                float(entry.get("start", 0)), float(entry.get("end", 0)),
                            ),
                        ).fetchone()
                    else:
                        entity_key = _json([scene_id, str(entry[key_name])])
                        existing_entry = connection.execute(
                            "SELECT translations_json, source_sheet FROM story_choices "
                            "WHERE profile = ? AND scene_id = ? AND choice_key = ?",
                            (profile, scene_id, str(entry[key_name])),
                        ).fetchone()
                    exists = existing_entry is not None
                    matches_source = bool(
                        exists
                        and _json(json.loads(existing_entry["translations_json"]))
                        == _json(entry.get("translations", {}))
                        and str(existing_entry["source_sheet"])
                        == str(entry.get("source_sheet", ""))
                    )
                    owned = entity_is_owned_by_source(entity_type, entity_key)
                    if exists and not owned and not matches_source:
                        # Keep rows owned by manual edits or legacy imports intact.
                        continue
                    scene_cursor = connection.execute(
                        """INSERT OR IGNORE INTO story_scenes(profile, scene_id, group_name,
                           scene_order, cases_json) VALUES (?, ?, 'Localization',
                           (SELECT COUNT(*) FROM story_scenes WHERE profile = ?), '[]')""",
                        (profile, scene_id, profile),
                    )
                    if scene_cursor.rowcount:
                        record_entity(
                            "scene", scene_id, str(entry.get("source_sheet", "")),
                            entry.get("source_row"),
                        )
                    if is_cue:
                        connection.execute(
                            """INSERT INTO subtitle_cues(profile, scene_id, cue_key, start_seconds,
                               end_seconds, translations_json, source_sheet) VALUES (?, ?, ?, ?, ?, ?, ?)
                               ON CONFLICT(profile, scene_id, cue_key, start_seconds, end_seconds)
                               DO UPDATE SET translations_json=excluded.translations_json,
                               source_sheet=excluded.source_sheet""",
                            (
                                profile, scene_id, str(entry[key_name]), float(entry.get("start", 0)),
                                float(entry.get("end", 0)), _json(entry.get("translations", {})),
                                str(entry.get("source_sheet", "")),
                            ),
                        )
                    else:
                        connection.execute(
                            """INSERT INTO story_choices(profile, scene_id, choice_key,
                               translations_json, source_sheet) VALUES (?, ?, ?, ?, ?)
                               ON CONFLICT(profile, scene_id, choice_key)
                               DO UPDATE SET translations_json=excluded.translations_json,
                               source_sheet=excluded.source_sheet""",
                            (
                                profile, scene_id, str(entry[key_name]),
                                _json(entry.get("translations", {})), str(entry.get("source_sheet", "")),
                            ),
                        )
                    record_entity(
                        entity_type, entity_key, str(entry.get("source_sheet", "")),
                        entry.get("source_row"),
                    )
                    if is_cue:
                        cue_count += 1
                    else:
                        choice_count += 1

        return {
            "source_id": source_id,
            "revision_hash": revision_hash,
            "previous_revision_hash": previous_hash,
            "changed": previous_hash != revision_hash,
            "row_count": sum(len(sheet["rows"]) for sheet in normalized_sheets),
            "sheet_count": len(normalized_sheets),
            "flow_scenes_added": scene_count,
            "flow_links_added": link_count,
            "testcases_imported": testcase_count,
            "subtitle_cues_imported": cue_count,
            "choices_imported": choice_count,
        }

    def list_source_revisions(self, profile: str, source_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM source_revisions WHERE profile = ? AND source_id = ? "
                    "ORDER BY imported_at_utc, revision_hash",
                    (profile, source_id),
                )
            ]

    def list_source_revision_rows(
        self, profile: str, source_id: str, revision_hash: str | None = None,
        sheet_name: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if revision_hash is None:
                row = connection.execute(
                    "SELECT revision_hash FROM source_revisions WHERE profile = ? "
                    "AND source_id = ? AND status = 'current'",
                    (profile, source_id),
                ).fetchone()
                if row is None:
                    return []
                revision_hash = str(row["revision_hash"])
            clauses = ["profile = ?", "source_id = ?", "revision_hash = ?"]
            params: list[Any] = [profile, source_id, revision_hash]
            if sheet_name is not None:
                clauses.append("sheet_name = ?")
                params.append(sheet_name)
            return [
                {**dict(row), "payload": json.loads(row["payload_json"])}
                for row in connection.execute(
                    "SELECT * FROM source_revision_rows WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY sheet_name, row_number",
                    params,
                )
            ]

    def list_source_entity_provenance(
        self,
        profile: str,
        *,
        source_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["profile = ?"]
        params: list[Any] = [profile]
        if source_id is not None:
            clauses.append("source_id = ?")
            params.append(source_id)
        if status is not None:
            if status not in {"active", "stale"}:
                raise ValueError("status must be 'active' or 'stale'")
            clauses.append("status = ?")
            params.append(status)
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM source_entity_provenance WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY source_id, entity_type, entity_key",
                    params,
                )
            ]

    def list_source_localization_candidates(
        self, profile: str, *, source_id: str | None = None,
        revision_hash: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["profile = ?"]
        params: list[Any] = [profile]
        if source_id is not None:
            clauses.append("source_id = ?")
            params.append(source_id)
        if revision_hash is not None:
            clauses.append("revision_hash = ?")
            params.append(revision_hash)
        with self._connect() as connection:
            rows = [
                dict(row) for row in connection.execute(
                    "SELECT * FROM source_localization_candidates WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY source_id, entity_type, entity_key, sheet_name, row_number",
                    params,
                )
            ]
        groups: dict[tuple[str, str, str], set[str]] = {}
        for row in rows:
            payload = json.loads(row["payload_json"])
            row["payload"] = payload
            for locale, text in payload.get("translations", {}).items():
                group = (row["revision_hash"], row["entity_type"], row["entity_key"] + ":" + locale)
                groups.setdefault(group, set()).add(str(text).strip())
        for row in rows:
            payload = row["payload"]
            row["conflicting_locales"] = [
                locale for locale in payload.get("translations", {})
                if len(groups.get((row["revision_hash"], row["entity_type"],
                                  row["entity_key"] + ":" + locale), set())) > 1
            ]
            row["has_conflict"] = bool(row["conflicting_locales"])
        return rows

    def record_unreal_telemetry_event(
        self, profile: str, session_id: str, payload: dict[str, Any]
    ) -> bool:
        """Append one already-validated read-only UE event; duplicates are idempotent."""
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO unreal_telemetry_events(
                   profile, session_id, build_id, event_id, sequence, emitted_at_utc,
                   received_at_utc, scene_id, event_type, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile, session_id, str(payload["build_id"]), str(payload["event_id"]),
                    int(payload["sequence"]), str(payload["emitted_at_utc"]),
                    datetime.now(UTC).isoformat(), str(payload["state"]["scene_id"]),
                    str(payload["event_type"]), _json(payload),
                ),
            )
            return cursor.rowcount == 1

    def list_unreal_telemetry_events(
        self, profile: str, session_id: str = "", limit: int = 200
    ) -> list[dict[str, Any]]:
        clauses = ["profile = ?"]
        params: list[Any] = [profile]
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        params.append(max(1, min(int(limit), 1000)))
        with self._connect() as connection:
            return [
                {**dict(row), "payload": json.loads(row["payload_json"])}
                for row in connection.execute(
                    "SELECT * FROM unreal_telemetry_events WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY session_id, sequence LIMIT ?",
                    params,
                )
            ]

    def list_source_sheets(
        self, profile: str, *, include_rows: bool = False
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                {
                    **dict(row),
                    **({"rows": json.loads(row["rows_json"])} if include_rows else {}),
                    "hyperlinks": json.loads(row["hyperlinks_json"]),
                }
                for row in connection.execute(
                    """SELECT s.*, r.revision_hash, r.source_url
                       FROM source_sheets AS s
                       LEFT JOIN source_revisions AS r
                         ON r.profile = s.profile AND r.source_id = s.source_id
                        AND r.status = 'current'
                       WHERE s.profile = ?
                       ORDER BY s.source_name, s.sheet_name""",
                    (profile,),
                )
            ]

    def store_game_memory(
        self, profile: str, memory_key: str, category: str, value: Any,
        source: str = "manual", confidence: float = 1.0,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO game_memory(profile, memory_key, category, value_json,
                   source, confidence, updated_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(profile, memory_key) DO UPDATE SET category=excluded.category,
                   value_json=excluded.value_json, source=excluded.source,
                   confidence=excluded.confidence, updated_at_utc=excluded.updated_at_utc""",
                (profile, memory_key, category, _json(value), source,
                 max(0.0, min(1.0, confidence)), datetime.now(UTC).isoformat()),
            )

    def list_game_memory(self, profile: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                {**dict(row), "value": json.loads(row["value_json"])}
                for row in connection.execute(
                    "SELECT * FROM game_memory WHERE profile = ? "
                    "ORDER BY category, memory_key", (profile,)
                )
            ]

    def replace_game_memory_search_index(
        self, profile: str, documents: list[dict[str, Any]]
    ) -> int:
        """Replace only one profile's derived FTS documents; SQLite source rows remain canonical."""
        with self._connect() as connection:
            connection.execute("DELETE FROM game_memory_fts WHERE profile = ?", (profile,))
            connection.executemany(
                """INSERT INTO game_memory_fts(profile, entity_type, entity_id,
                   title, body, citation) VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        profile, str(item["entity_type"]), str(item["entity_id"]),
                        str(item.get("title", "")), str(item.get("body", "")),
                        _json(item.get("citation", {})),
                    )
                    for item in documents
                ],
            )
        return len(documents)

    def search_game_memory(
        self, profile: str, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Search one game's derived FTS index and return stable entity/citation fields."""
        import re

        terms = re.findall(r"[^\W_]+", query.casefold(), flags=re.UNICODE)
        if not terms:
            return []
        quoted = ['"' + term.replace('"', '""') + '"' for term in terms]
        match_options = ['"' + " ".join(terms).replace('"', '""') + '"']
        if len(terms) > 1:
            match_options.extend((" AND ".join(quoted), " OR ".join(quoted)))
        with self._connect() as connection:
            bounded_limit = max(1, min(int(limit), 200))
            for match in match_options:
                rows = connection.execute(
                    """SELECT entity_type, entity_id, title,
                       snippet(game_memory_fts, 4, '[', ']', ' … ', 16) AS snippet,
                       citation, bm25(game_memory_fts) AS rank
                       FROM game_memory_fts WHERE profile = ? AND game_memory_fts MATCH ?
                       ORDER BY rank LIMIT ?""",
                    (profile, match, bounded_limit),
                )
                results = [
                    {
                        **dict(row),
                        "citation": json.loads(row["citation"]),
                        "profile": profile,
                    }
                    for row in rows
                ]
                if results:
                    return results
            return []

    def list_story_evidence(self, profile: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM story_evidence WHERE profile = ? "
                "ORDER BY created_at_utc DESC LIMIT ?",
                (profile, max(1, min(limit, 500))),
            )
            return [{**dict(row), "result": json.loads(row["result_json"])} for row in rows]

    def seed_testcases(self, profile: str, cases: list[dict[str, Any]]) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            for case in cases:
                case_id = str(case.get("case_id", case.get("id", ""))).strip()
                if not case_id:
                    continue
                connection.execute(
                    """INSERT INTO test_cases(profile, case_id, scene_id, source_row,
                       group_name, source_status, feedback_tags_json, source_json, updated_at_utc)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(profile, case_id) DO UPDATE SET scene_id=excluded.scene_id,
                       source_row=excluded.source_row, group_name=excluded.group_name,
                       source_status=excluded.source_status,
                       feedback_tags_json=excluded.feedback_tags_json,
                       source_json=excluded.source_json, updated_at_utc=excluded.updated_at_utc""",
                    (
                        profile,
                        case_id,
                        str(case.get("scene_id", "")),
                        case.get("source_row"),
                        str(case.get("group", "")),
                        str(case.get("final_result", case.get("status", ""))),
                        _json(case.get("feedback_tags", [])),
                        _json(case),
                        now,
                    ),
                )
            return connection.execute(
                "SELECT COUNT(*) FROM test_cases WHERE profile = ?", (profile,)
            ).fetchone()[0]

    def save_story_project(self, profile: str, payload: dict[str, Any]) -> None:
        now = datetime.now(UTC).isoformat()
        self.register_game(
            profile,
            str(payload.get("title", "HighSchool Blood")),
            "fmv_visual_novel",
            "5173380" if profile == "highschoolblood-demo" else "",
        )
        scenes = payload.get("scenes", {})
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO story_projects(profile, title, source_summary_json,
                   required_locales_json, conflicts_json, updated_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(profile) DO UPDATE SET title=excluded.title,
                   source_summary_json=excluded.source_summary_json,
                   required_locales_json=excluded.required_locales_json,
                   conflicts_json=excluded.conflicts_json, updated_at_utc=excluded.updated_at_utc""",
                (
                    profile,
                    str(payload.get("title", "HighSchool Blood")),
                    _json(payload.get("source_summary", {})),
                    _json(payload.get("required_locales", ["th", "en"])),
                    _json(payload.get("conflicts", [])),
                    now,
                ),
            )
            connection.execute("DELETE FROM story_scenes WHERE profile = ?", (profile,))
            connection.execute("DELETE FROM patch_items WHERE profile = ?", (profile,))
            connection.executemany(
                """INSERT INTO patch_items(profile, item_order, version, build_id, category,
                   text, scene_ids_json) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        profile,
                        index,
                        str(item.get("version", "")),
                        str(item.get("build_id", "")),
                        str(item.get("category", "")),
                        str(item.get("text", "")),
                        _json(item.get("scene_ids", [])),
                    )
                    for index, item in enumerate(payload.get("patch_items", []))
                ],
            )
            for scene_id, scene in scenes.items():
                connection.execute(
                    """INSERT INTO story_scenes(profile, scene_id, group_name, scene_order, cases_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        profile,
                        scene_id,
                        str(scene.get("group", "Unassigned")),
                        int(scene.get("order", 0)),
                        _json(scene.get("cases", [])),
                    ),
                )
                connection.executemany(
                    """INSERT INTO subtitle_cues(profile, scene_id, cue_key, start_seconds,
                       end_seconds, translations_json, source_sheet) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            profile,
                            scene_id,
                            str(cue.get("key", "")),
                            float(cue.get("start", 0)),
                            float(cue.get("end", 0)),
                            _json(cue.get("translations", {})),
                            str(cue.get("source_sheet", "")),
                        )
                        for cue in scene.get("cues", [])
                    ],
                )
                connection.executemany(
                    """INSERT INTO story_choices(profile, scene_id, choice_key,
                       translations_json, source_sheet) VALUES (?, ?, ?, ?, ?)""",
                    [
                        (
                            profile,
                            scene_id,
                            str(choice.get("key", "")),
                            _json(choice.get("translations", {})),
                            str(choice.get("source_sheet", "")),
                        )
                        for choice in scene.get("choices", [])
                    ],
                )
                connection.executemany(
                    """INSERT INTO story_links(profile, source_scene, target_scene, choice_key)
                       VALUES (?, ?, ?, ?)""",
                    [
                        (profile, scene_id, link["target"], str(link.get("choice_key", "")))
                        for link in scene.get("outgoing", [])
                    ],
                )

    def load_story_project(self, profile: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            project = connection.execute(
                "SELECT * FROM story_projects WHERE profile = ?", (profile,)
            ).fetchone()
            if project is None:
                return None
            provenance_rows = connection.execute(
                "SELECT entity_type, entity_key, status FROM source_entity_provenance WHERE profile = ?",
                (profile,),
            ).fetchall()
            imported_entities = {
                (str(row["entity_type"]), str(row["entity_key"]))
                for row in provenance_rows
            }
            active_entities = {
                (str(row["entity_type"]), str(row["entity_key"]))
                for row in provenance_rows if row["status"] == "active"
            }

            def is_current_import(entity_type: str, entity_key: str) -> bool:
                identity = (entity_type, entity_key)
                return identity not in imported_entities or identity in active_entities

            scenes: dict[str, dict[str, Any]] = {}
            for row in connection.execute(
                "SELECT * FROM story_scenes WHERE profile = ? ORDER BY scene_order, scene_id",
                (profile,),
            ):
                scene_id = row["scene_id"]
                scenes[scene_id] = {
                    "scene_id": scene_id,
                    "group": row["group_name"],
                    "order": row["scene_order"],
                    "cases": json.loads(row["cases_json"]),
                    "cues": [],
                    "choices": [],
                    "outgoing": [],
                }
            for row in connection.execute(
                "SELECT * FROM subtitle_cues WHERE profile = ? ORDER BY start_seconds",
                (profile,),
            ):
                entity_key = _json([
                    str(row["scene_id"]), str(row["cue_key"]),
                    float(row["start_seconds"]), float(row["end_seconds"]),
                ])
                if not is_current_import("cue", entity_key):
                    continue
                scenes[row["scene_id"]]["cues"].append(
                    {
                        "key": row["cue_key"],
                        "scene_id": row["scene_id"],
                        "start": row["start_seconds"],
                        "end": row["end_seconds"],
                        "translations": json.loads(row["translations_json"]),
                        "source_sheet": row["source_sheet"],
                    }
                )
            for row in connection.execute(
                "SELECT * FROM story_choices WHERE profile = ? ORDER BY choice_key",
                (profile,),
            ):
                entity_key = _json([str(row["scene_id"]), str(row["choice_key"])])
                if not is_current_import("choice", entity_key):
                    continue
                scenes[row["scene_id"]]["choices"].append(
                    {
                        "key": row["choice_key"],
                        "scene_id": row["scene_id"],
                        "translations": json.loads(row["translations_json"]),
                        "source_sheet": row["source_sheet"],
                    }
                )
            for row in connection.execute(
                "SELECT * FROM story_links WHERE profile = ? ORDER BY source_scene, choice_key",
                (profile,),
            ):
                entity_key = _json([
                    str(row["source_scene"]), str(row["target_scene"]),
                    str(row["choice_key"]),
                ])
                if not is_current_import("link", entity_key):
                    continue
                scenes[row["source_scene"]]["outgoing"].append(
                    {"target": row["target_scene"], "choice_key": row["choice_key"]}
                )
        return {
            "title": project["title"],
            "source_summary": json.loads(project["source_summary_json"]),
            "required_locales": json.loads(project["required_locales_json"]),
            "conflicts": json.loads(project["conflicts_json"]),
            "patch_items": self._load_patch_items(profile),
            "scenes": scenes,
        }

    def _load_patch_items(self, profile: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                {
                    "version": row["version"],
                    "build_id": row["build_id"],
                    "category": row["category"],
                    "text": row["text"],
                    "scene_ids": json.loads(row["scene_ids_json"]),
                }
                for row in connection.execute(
                    "SELECT * FROM patch_items WHERE profile = ? ORDER BY item_order", (profile,)
                )
            ]

    def record_run(self, manifest: dict[str, Any], manifest_path: Path) -> None:
        profile = str(manifest.get("profile", "unknown"))
        self.register_game(
            profile,
            str(manifest.get("game", profile)),
            str(manifest.get("game_type", "fmv_visual_novel")),
            str(manifest.get("steam_app_id", "")),
        )
        testcase_snapshot = (
            _resource_base() / "qa_framework" / "testcases" / "highschool_blood_cases.json"
        )
        if not testcase_snapshot.is_file():
            testcase_snapshot = ROOT / "qa_framework" / "testcases" / "highschool_blood_cases.json"
        if profile == "highschoolblood-demo" and testcase_snapshot.is_file():
            payload = json.loads(testcase_snapshot.read_text(encoding="utf-8"))
            self.seed_testcases(profile, payload.get("cases", []))
            if self.load_story_project(profile) is None:
                self._seed_story_scenes(profile, payload)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO qa_runs(run_id, profile, build_id, status, qa_status,
                   started_at_utc, finished_at_utc, manifest_path, trace_path, report_path,
                   manifest_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(run_id) DO UPDATE SET status=excluded.status,
                   qa_status=excluded.qa_status, finished_at_utc=excluded.finished_at_utc,
                   trace_path=excluded.trace_path, report_path=excluded.report_path,
                   manifest_json=excluded.manifest_json""",
                (
                    str(manifest.get("run_id", manifest_path.parent.name)),
                    profile,
                    str(manifest.get("steam_build_id", manifest.get("build_id", ""))),
                    str(manifest.get("status", "UNKNOWN")),
                    str(manifest.get("qa_status", "UNASSERTED")),
                    str(manifest.get("started_at_utc", datetime.now(UTC).isoformat())),
                    manifest.get("finished_at_utc"),
                    str(manifest_path),
                    str(manifest.get("trace", "")),
                    str(manifest.get("session_report", manifest.get("report_html", ""))),
                    _json(manifest),
                ),
            )
        case_id = str(manifest.get("testcase_id", "")).strip()
        if case_id:
            self.record_case_result(
                str(manifest.get("run_id", manifest_path.parent.name)),
                case_id,
                str(manifest.get("qa_status", "UNASSERTED")),
                expected=manifest.get("expected", []),
                observed=f"Run status: {manifest.get('status', 'UNKNOWN')}",
                evidence=[
                    str(manifest_path),
                    str(manifest.get("trace", "")),
                    str(manifest.get("session_report", "")),
                ],
            )

    def create_qa_campaign(
        self, *, campaign_id: str, profile: str, idempotency_key: str,
        status: str, selected_case_ids: list[str], selected_categories: list[str],
        run_ids: list[str], result: dict[str, Any] | None = None,
    ) -> bool:
        """Persist one campaign; nonempty idempotency keys are unique per profile."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute(
                """SELECT 1 FROM qa_campaigns
                   WHERE profile = ? AND status IN ('STARTING', 'RUNNING', 'RECOVERY_REQUIRED')
                   LIMIT 1""",
                (profile,),
            ).fetchone()
            if active is not None:
                return False
            cursor = connection.execute(
                """INSERT OR IGNORE INTO qa_campaigns(
                   campaign_id, profile, idempotency_key, status, qa_status,
                   selected_case_ids_json, selected_categories_json, run_ids_json,
                   started_at_utc, result_json)
                   VALUES (?, ?, ?, ?, 'UNASSERTED', ?, ?, ?, ?, ?)""",
                (
                    campaign_id, profile, idempotency_key, status,
                    _json(selected_case_ids), _json(selected_categories), _json(run_ids),
                    datetime.now(UTC).isoformat(), _json(result or {}),
                ),
            )
            return cursor.rowcount == 1

    def get_qa_campaign(
        self, campaign_id: str = "", *, profile: str = "", idempotency_key: str = ""
    ) -> dict[str, Any] | None:
        if not campaign_id and not (profile and idempotency_key):
            raise ValueError("Provide a campaign_id or profile with an idempotency_key")
        where, params = (
            ("campaign_id = ?", [campaign_id])
            if campaign_id
            else ("profile = ? AND idempotency_key = ?", [profile, idempotency_key])
        )
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM qa_campaigns WHERE {where}", params
            ).fetchone()
            attempts = (
                connection.execute(
                    "SELECT * FROM qa_campaign_attempts WHERE campaign_id = ? ORDER BY attempt_number",
                    (row["campaign_id"],),
                ).fetchall()
                if row is not None
                else []
            )
        if row is None:
            return None
        return {
            **dict(row),
            "selected_case_ids": json.loads(row["selected_case_ids_json"]),
            "selected_categories": json.loads(row["selected_categories_json"]),
            "run_ids": json.loads(row["run_ids_json"]),
            "result": json.loads(row["result_json"]),
            "attempts": [self._decode_qa_campaign_attempt(attempt) for attempt in attempts],
        }

    @staticmethod
    def _decode_qa_campaign_attempt(row: sqlite3.Row) -> dict[str, Any]:
        return {**dict(row), "result": json.loads(row["result_json"])}

    def reserve_qa_campaign_attempt(
        self, campaign_id: str, retry_key: str
    ) -> dict[str, Any]:
        """Atomically reserve one explicit retry attempt without duplicating a worker."""
        key = retry_key.strip()
        if not key or len(key) > 128:
            raise ValueError("retry_key must contain 1..128 characters")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM qa_campaigns WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
            if row is None:
                return {"created": False, "error": "campaign not found"}
            previous = connection.execute(
                """SELECT * FROM qa_campaign_attempts
                   WHERE campaign_id = ? AND retry_key = ?""",
                (campaign_id, key),
            ).fetchone()
            if previous is not None:
                return {
                    "created": False,
                    "reused": True,
                    "attempt": self._decode_qa_campaign_attempt(previous),
                }
            if row["status"] not in {"INTERRUPTED", "FAILED", "BLOCKED", "STOPPED"}:
                return {"created": False, "error": "campaign is not in a retryable state"}
            active = connection.execute(
                """SELECT campaign_id FROM qa_campaigns WHERE profile = ?
                   AND status IN ('STARTING', 'RUNNING', 'RECOVERY_REQUIRED')
                   AND campaign_id <> ? LIMIT 1""",
                (row["profile"], campaign_id),
            ).fetchone()
            if active is not None:
                return {"created": False, "error": "another campaign is active for this profile"}
            attempt_number = int(connection.execute(
                "SELECT COUNT(*) FROM qa_campaign_attempts WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0]) + 1
            attempt_id = uuid.uuid4().hex
            now = datetime.now(UTC).isoformat()
            connection.execute(
                """INSERT INTO qa_campaign_attempts(
                   attempt_id, campaign_id, retry_key, attempt_number, status,
                   qa_status, started_at_utc, result_json)
                   VALUES (?, ?, ?, ?, 'STARTING', 'UNASSERTED', ?, ?)""",
                (attempt_id, campaign_id, key, attempt_number, now, _json({"retry_key": key})),
            )
            campaign_result = json.loads(row["result_json"])
            for field in ("worker_pid", "worker_created_epoch", "worker_run_dir"):
                campaign_result.pop(field, None)
            campaign_result["active_attempt_id"] = attempt_id
            connection.execute(
                """UPDATE qa_campaigns SET status = 'STARTING', qa_status = 'UNASSERTED',
                   finished_at_utc = NULL, result_json = ? WHERE campaign_id = ?""",
                (_json(campaign_result), campaign_id),
            )
            attempt = connection.execute(
                "SELECT * FROM qa_campaign_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            return {
                "created": True,
                "attempt": self._decode_qa_campaign_attempt(attempt),
            }

    def update_qa_campaign_attempt(
        self, campaign_id: str, attempt_id: str, *, status: str,
        qa_status: str = "UNASSERTED", run_id: str = "",
        result: dict[str, Any] | None = None,
    ) -> bool:
        """Update an attempt and its parent campaign in one SQLite transaction."""
        terminal = status not in {"STARTING", "RUNNING", "RECOVERY_REQUIRED"}
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            attempt = connection.execute(
                """SELECT * FROM qa_campaign_attempts
                   WHERE attempt_id = ? AND campaign_id = ?""",
                (attempt_id, campaign_id),
            ).fetchone()
            if attempt is None:
                return False
            previous_result = json.loads(attempt["result_json"])
            merged_result = {**previous_result, **(result or {})}
            resolved_run_id = run_id or str(attempt["run_id"] or "")
            connection.execute(
                """UPDATE qa_campaign_attempts SET status = ?, qa_status = ?, run_id = ?,
                   finished_at_utc = ?, result_json = ? WHERE attempt_id = ?""",
                (
                    status, qa_status, resolved_run_id, now if terminal else None,
                    _json(merged_result), attempt_id,
                ),
            )
            campaign = connection.execute(
                "SELECT run_ids_json, result_json FROM qa_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if campaign is None:
                return False
            run_ids = json.loads(campaign["run_ids_json"])
            if resolved_run_id and resolved_run_id not in run_ids:
                run_ids.append(resolved_run_id)
            campaign_result = json.loads(campaign["result_json"])
            campaign_result.update({
                "run_id": resolved_run_id,
                "latest_attempt_id": attempt_id,
                "latest_retry_key": attempt["retry_key"],
                "latest_run_id": resolved_run_id,
            })
            campaign_result.pop("active_attempt_id", None)
            for key in ("worker_pid", "worker_created_epoch", "worker_run_dir"):
                if key in merged_result:
                    campaign_result[key] = merged_result[key]
            connection.execute(
                """UPDATE qa_campaigns SET status = ?, qa_status = ?, finished_at_utc = ?,
                   run_ids_json = ?, result_json = ? WHERE campaign_id = ?""",
                (
                    status, qa_status, now if terminal else None,
                    _json(run_ids), _json(campaign_result), campaign_id,
                ),
            )
            return True

    def update_qa_campaign(
        self, campaign_id: str, *, status: str, qa_status: str = "UNASSERTED",
        finished_at_utc: str | None = None, result: dict[str, Any] | None = None,
        run_ids: list[str] | None = None,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE qa_campaigns SET status = ?, qa_status = ?,
                   finished_at_utc = COALESCE(?, finished_at_utc), result_json = ?,
                   run_ids_json = COALESCE(?, run_ids_json)
                   WHERE campaign_id = ?""",
                (
                    status, qa_status, finished_at_utc, _json(result or {}),
                    _json(run_ids) if run_ids is not None else None, campaign_id,
                ),
            )
            return cursor.rowcount == 1

    def list_qa_campaigns(self, profile: str = "", limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM qa_campaigns WHERE (? = '' OR profile = ?)
                   ORDER BY started_at_utc DESC LIMIT ?""",
                (profile, profile, max(1, min(int(limit), 200))),
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                attempts = connection.execute(
                    """SELECT * FROM qa_campaign_attempts WHERE campaign_id = ?
                       ORDER BY attempt_number""",
                    (row["campaign_id"],),
                ).fetchall()
                result.append({
                    **dict(row),
                    "selected_case_ids": json.loads(row["selected_case_ids_json"]),
                    "selected_categories": json.loads(row["selected_categories_json"]),
                    "run_ids": json.loads(row["run_ids_json"]),
                    "result": json.loads(row["result_json"]),
                    "attempts": [self._decode_qa_campaign_attempt(attempt) for attempt in attempts],
                })
        return result

    def _seed_story_scenes(self, profile: str, snapshot: dict[str, Any]) -> None:
        scenes: dict[str, dict[str, Any]] = {}
        for case in snapshot.get("cases", []):
            scene_id = str(case.get("scene_id", "")).strip()
            if not scene_id:
                continue
            scene = scenes.setdefault(
                scene_id,
                {
                    "group": str(case.get("group", "Unassigned")),
                    "order": len(scenes),
                    "cases": [],
                    "cues": [],
                    "choices": [],
                    "outgoing": [],
                },
            )
            scene["cases"].append(case)
        summary = snapshot.get("row_level_summary", {})
        self.save_story_project(
            profile,
            {
                "title": str(snapshot.get("game", "HighSchool Blood")),
                "source_summary": {
                    "testcase_snapshot": snapshot.get("source", {}).get("workbook", ""),
                    "qa_cases": len(snapshot.get("cases", [])),
                    "scene_ids": len(scenes),
                    "qa_statuses": summary.get("statuses", {}),
                    "snapshot_only": True,
                },
                "required_locales": ["th", "en"],
                "conflicts": [],
                "patch_items": [],
                "scenes": scenes,
            },
        )

    def record_case_result(
        self,
        run_id: str,
        case_id: str,
        status: str,
        expected: Any = None,
        observed: str = "",
        assertions: Any = None,
        evidence: Any = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO testcase_results(run_id, case_id, status, expected_json,
                   observed, assertions_json, evidence_json, updated_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(run_id, case_id) DO UPDATE SET status=excluded.status,
                   expected_json=excluded.expected_json, observed=excluded.observed,
                   assertions_json=excluded.assertions_json, evidence_json=excluded.evidence_json,
                   updated_at_utc=excluded.updated_at_utc""",
                (
                    run_id,
                    case_id,
                    status,
                    _json(expected or []),
                    observed,
                    _json(assertions or []),
                    _json(evidence or []),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def record_feedback(
        self,
        feedback_id: str,
        category: str,
        note: str,
        run_id: str = "",
        case_id: str = "",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO qa_feedback(feedback_id, run_id, case_id, category, note, created_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    feedback_id,
                    run_id or None,
                    case_id,
                    category,
                    note,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def list_runs(self, profile: str = "", limit: int = 25) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT run_id, profile, build_id, status, qa_status, started_at_utc,
                   finished_at_utc, manifest_path, trace_path, report_path FROM qa_runs
                   WHERE (? = '' OR profile = ?) ORDER BY started_at_utc DESC LIMIT ?""",
                (profile, profile, max(1, min(limit, 200))),
            )
            return [dict(row) for row in rows]

    def list_testcase_results(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM testcase_results WHERE run_id = ? ORDER BY case_id", (run_id,)
            )
            return [
                {
                    **dict(row),
                    "expected": json.loads(row["expected_json"]),
                    "assertions": json.loads(row["assertions_json"]),
                    "evidence": json.loads(row["evidence_json"]),
                }
                for row in rows
            ]

    def list_feedback(self, run_id: str) -> list[dict[str, Any]]:
        """List review notes attached to one QA run, in creation order."""
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM qa_feedback WHERE run_id = ? ORDER BY created_at_utc, feedback_id",
                    (run_id,),
                )
            ]

    def list_testcase_sources(self, profile: str) -> dict[str, dict[str, Any]]:
        """Return the stored source record for each testcase in one game profile."""
        with self._connect() as connection:
            provenance_rows = connection.execute(
                "SELECT entity_key, status FROM source_entity_provenance "
                "WHERE profile = ? AND entity_type = 'testcase'",
                (profile,),
            ).fetchall()
            imported = {str(row["entity_key"]) for row in provenance_rows}
            active = {
                str(row["entity_key"]) for row in provenance_rows if row["status"] == "active"
            }
            rows = connection.execute(
                "SELECT case_id, source_json FROM test_cases WHERE profile = ?",
                (profile,),
            )
            return {
                str(row["case_id"]): json.loads(row["source_json"])
                for row in rows
                if str(row["case_id"]) not in imported or str(row["case_id"]) in active
            }

    def story_summary(self, profile: str) -> dict[str, Any]:
        with self._connect() as connection:
            counts: dict[str, int] = {}
            for key, table in (
                ("scenes", "story_scenes"),
                ("subtitles", "subtitle_cues"),
                ("choices", "story_choices"),
                ("links", "story_links"),
                ("testcases", "test_cases"),
            ):
                row = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE profile = ?", (profile,)
                ).fetchone()
                counts[key] = int(row[0])
            for key, table in (
                ("evidence", "story_evidence"),
                ("source_sheets", "source_sheets"),
                ("memory_facts", "game_memory"),
            ):
                row = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE profile = ?", (profile,)
                ).fetchone()
                counts[key] = int(row[0])
            project = connection.execute(
                "SELECT updated_at_utc FROM story_projects WHERE profile = ?", (profile,)
            ).fetchone()
            return {
                "profile": profile,
                **counts,
                "updated_at_utc": project["updated_at_utc"] if project else None,
                "database": str(self.path),
            }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
