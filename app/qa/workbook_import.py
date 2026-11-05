from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.database.database import QADatabase, sanitize_profile_key
from app.qa.story_timeline import (
    _parse_choice_row,
    _parse_cue_row,
    _read_text_source,
    _read_workbook_source,
)


def import_source_document(
    database: QADatabase,
    *,
    profile: str,
    game_name: str,
    game_type: str,
    source_url: str,
) -> dict[str, Any]:
    """Archive a linked Google Doc in the same per-game source/memory index."""
    match = re.search(r"/document/d/([\w-]+)", source_url)
    if not match:
        raise ValueError("ใส่ URL Google Docs ที่มีสิทธิ์เปิดอ่าน")
    content, source_name = _read_text_source(source_url)
    database.register_game(profile, game_name, game_type)
    if database.load_story_project(profile) is None:
        database.save_story_project(
            profile,
            {
                "title": game_name,
                "source_summary": {"imported_workbooks": []},
                "required_locales": [],
                "conflicts": [],
                "patch_items": [],
                "scenes": {},
            },
        )
    lines = content.splitlines()
    source_id = f"doc-{match.group(1)}"
    database.save_source_sheets(
        profile,
        source_id,
        source_name,
        [
            {
                "sheet_name": "Document text",
                "rows": [[line] for line in lines],
                "row_count": len(lines),
                "column_count": 1,
                "hyperlinks": [],
            }
        ],
        source_url=source_url,
    )
    database.store_game_memory(
        profile,
        f"source.document.{match.group(1)}",
        "source_document",
        {"name": source_name, "text": content, "source_url": source_url},
        source=source_url,
    )
    archive_dir = database.path.parent / "sources"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f"{sanitize_profile_key(profile)}-{source_id}.json"
    archive.write_text(
        json.dumps(
            {
                "game": game_name,
                "profile": profile,
                "source": {"name": source_name, "url": source_url},
                "sheets": [{"sheet_name": "Document text", "rows": [[line] for line in lines]}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_index(database.path.parents[2], profile, game_name, database, archive)
    return {
        "profile": profile,
        "source_name": source_name,
        "lines": len(lines),
        "archive_path": str(archive),
    }


def import_source_workbook(
    database: QADatabase,
    *,
    profile: str,
    game_name: str,
    game_type: str,
    source_url: str,
) -> dict[str, Any]:
    """Archive every visible sheet, hyperlinks, flow nodes, checklist rows, and memory."""
    match = re.search(r"/spreadsheets/d/([\w-]+)", source_url)
    if not match:
        raise ValueError("ใส่ URL Google Sheets ที่มีสิทธิ์เปิดอ่าน")
    source_id = match.group(1)
    workbook_data, source_name = _read_workbook_source(source_url)
    workbook = load_workbook(workbook_data, read_only=False, data_only=True)
    sheets: list[dict[str, Any]] = []
    flow_scenes: list[dict[str, Any]] = []
    flow_links: list[dict[str, str]] = []
    cases: list[dict[str, Any]] = []
    memory_facts: list[tuple[str, str, Any]] = []
    localization_cues: dict[tuple[str, str, float, float], dict[str, Any]] = {}
    localization_choices: dict[tuple[str, str], dict[str, Any]] = {}
    localization_candidates: list[dict[str, Any]] = []
    total_nonempty_rows = 0
    total_hyperlinks = 0

    try:
        for worksheet in workbook.worksheets:
            raw_rows: list[list[Any]] = []
            hyperlinks: list[dict[str, str]] = []
            nonempty_count = 0
            column_count = 0
            for row in worksheet.iter_rows():
                values = [_json_value(cell.value) for cell in row]
                while values and values[-1] is None:
                    values.pop()
                if any(value is not None and str(value).strip() for value in values):
                    nonempty_count += 1
                    column_count = max(column_count, len(values))
                raw_rows.append(values)
                for cell in row:
                    if cell.hyperlink and cell.hyperlink.target:
                        hyperlinks.append(
                            {
                                "cell": cell.coordinate,
                                "label": str(cell.value or "").strip(),
                                "target": str(cell.hyperlink.target),
                            }
                        )

            data = {
                "sheet_name": worksheet.title,
                "rows": raw_rows,
                "row_count": nonempty_count,
                "column_count": column_count,
                "hyperlinks": hyperlinks,
            }
            sheets.append(data)
            total_nonempty_rows += nonempty_count
            total_hyperlinks += len(hyperlinks)
            scenes_in_sheet, links_in_sheet = _flow_graph(worksheet.title, raw_rows)
            flow_scenes.extend(scenes_in_sheet)
            flow_links.extend(links_in_sheet)
            cases.extend(_checklist_cases(worksheet.title, raw_rows))
            _collect_localization(
                worksheet.title, raw_rows, localization_cues, localization_choices,
                localization_candidates,
            )

            if "mini" in worksheet.title.casefold():
                statements = [
                    str(value).strip()
                    for row in raw_rows
                    for value in row
                    if isinstance(value, str) and value.strip()
                ]
                if statements:
                    memory_facts.append(
                        (f"minigame.sheet.{worksheet.title}", "minigame", statements)
                    )
    finally:
        workbook.close()

    cues = list(localization_cues.values())
    choices = list(localization_choices.values())
    # Parse every workbook artifact before this call; raw source rows and all
    # normalized graph writes then commit or roll back as one database txn.
    unique_scenes: dict[str, dict[str, Any]] = {}
    for scene in flow_scenes:
        unique_scenes.setdefault(scene["scene_id"], {**scene, "cases": []})
    snapshot = database.sync_workbook_import(
        profile=profile,
        display_name=game_name,
        game_type=game_type,
        source_id=source_id,
        source_name=source_name,
        source_url=source_url,
        sheets=sheets,
        scenes=list(unique_scenes.values()),
        links=flow_links,
        cases=cases,
        cues=cues,
        choices=choices,
        localization_candidates=localization_candidates,
    )
    sheet_count = snapshot["sheet_count"]
    candidates = database.list_source_localization_candidates(
        profile, source_id=source_id, revision_hash=snapshot["revision_hash"]
    )
    conflict_entities = {
        (item["entity_type"], item["entity_key"])
        for item in candidates if item["has_conflict"]
    }

    summary = {
        "profile": profile,
        "source_id": source_id,
        "source_name": source_name,
        "source_url": source_url,
        "revision_hash": snapshot["revision_hash"],
        "previous_revision_hash": snapshot["previous_revision_hash"],
        "source_changed": snapshot["changed"],
        "sheet_count": sheet_count,
        "nonempty_rows": total_nonempty_rows,
        "hyperlinks": total_hyperlinks,
        "source_rows": snapshot["row_count"],
        "flow_scenes_added": snapshot["flow_scenes_added"],
        "flow_links_added": snapshot["flow_links_added"],
        "testcases_imported": snapshot["testcases_imported"],
        "subtitle_cues_imported": snapshot["subtitle_cues_imported"],
        "choices_imported": snapshot["choices_imported"],
        "localization_candidates": len(candidates),
        "localization_conflicts": len(conflict_entities),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sheets": [
            {
                "name": sheet["sheet_name"],
                "rows": sheet["row_count"],
                "columns": sheet["column_count"],
                "hyperlinks": len(sheet["hyperlinks"]),
            }
            for sheet in sheets
        ],
    }
    database.store_game_memory(
        profile,
        f"source.workbook.{source_id}",
        "source_import",
        summary,
        source=source_url,
    )
    for fact_key, category, value in memory_facts:
        database.store_game_memory(profile, fact_key, category, value, source=source_url)
    if profile.startswith("highschoolblood"):
        for key, category, value in (
            (
                "choice.visual_toggle",
                "user_requirement",
                {"enabled": "show choices as gray circles", "disabled": "show all choice options"},
            ),
            (
                "choice.go_left.options",
                "user_requirement",
                {
                    "direct_options": 4,
                    "fifth_option": "timer choice when no option is selected before timeout",
                },
            ),
            (
                "settings.language",
                "user_requirement",
                "Language can be selected in settings before entering the game.",
            ),
        ):
            database.store_game_memory(
                profile, key, category, value, source="User-provided QA requirements"
            )

    root = database.path.parents[2]
    archive_dir = database.path.parent / "sources"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f"{sanitize_profile_key(profile)}-{source_id}.json"
    archive.write_text(
        json.dumps(
            {
                "game": game_name,
                "profile": profile,
                "source": summary,
                "sheets": sheets,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_index(root, profile, game_name, database, archive)
    return {
        **summary,
        "archive_path": str(archive),
        "index_path": str(root / "reports" / f"source-workbooks-{profile}.md"),
    }


def _flow_graph(
    sheet_name: str, rows: list[list[Any]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    flow_row = next(
        (
            row_index
            for row_index, row in enumerate(rows[:4])
            if any(
                isinstance(value, str) and value.strip().casefold() == "flow"
                for value in row
            )
        ),
        None,
    )
    if flow_row is None:
        return [], []
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    links: list[dict[str, str]] = []
    link_keys: set[tuple[str, str, str]] = set()
    prior_columns: list[str] = []
    for source_row, row in enumerate(rows[flow_row:], start=flow_row + 1):
        if len(prior_columns) < len(row):
            prior_columns.extend([""] * (len(row) - len(prior_columns)))
        for column, value in enumerate(row):
            if not isinstance(value, str):
                continue
            cleaned = value.strip()
            if not cleaned:
                if column >= len(prior_columns):
                    prior_columns.extend([""] * (column + 1 - len(prior_columns)))
                continue
            parts = [part.strip() for part in cleaned.splitlines() if part.strip()]
            candidate = parts[0] if parts else ""
            if not candidate or candidate.casefold() in {"flow", "ending", "gameover"}:
                if candidate.casefold() not in {"ending", "gameover"}:
                    if candidate:
                        prior_columns[column] = ""
                    continue
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", candidate):
                if candidate.casefold() not in {"ending", "gameover"}:
                    prior_columns[column] = ""
                    continue
            if not (
                "_" in candidate
                or any(char.isdigit() for char in candidate)
                or candidate.casefold() in {"ending", "gameover"}
            ):
                prior_columns[column] = ""
                continue
            if candidate not in seen:
                seen.add(candidate)
                results.append({
                    "scene_id": candidate, "group": sheet_name,
                    "source_sheet": sheet_name, "source_row": source_row,
                })
            parent = prior_columns[column - 1] if column > 0 else ""
            if parent and parent != candidate:
                choice_key = parts[1] if len(parts) > 1 else ""
                identity = (parent, candidate, choice_key)
                if identity not in link_keys:
                    link_keys.add(identity)
                    links.append({
                        "source": parent, "target": candidate, "choice_key": choice_key,
                        "source_sheet": sheet_name, "source_row": source_row,
                    })
            prior_columns[column] = candidate
    return results, links


def _collect_localization(
    sheet_name: str,
    rows: list[list[Any]],
    cue_store: dict[tuple[str, str, float, float], dict[str, Any]],
    choice_store: dict[tuple[str, str], dict[str, Any]],
    candidate_store: list[dict[str, Any]] | None = None,
) -> None:
    cue_priority = {"Luna Subtitle": 0, "ชีต11": 1, "Subtitles_Demo": 2, "Subtitles": 3}
    choice_priority = {"Luna Choice": 0, "ชีต10": 1}
    for row_index, header_row in enumerate(rows):
        headers = {
            str(value).strip(): index
            for index, value in enumerate(header_row)
            if isinstance(value, str) and value.strip()
        }
        is_cue_sheet = {"Key", "Time_Start", "Time_End"} <= headers.keys()
        is_choice_sheet = "Key" in headers and "lang-en" in headers
        if not is_cue_sheet and not is_choice_sheet:
            continue
        for source_row, row in enumerate(rows[row_index + 1 :], start=row_index + 2):
            values = tuple(row)
            parsed = (
                _parse_cue_row(sheet_name, headers, values, source_row)
                if is_cue_sheet
                else _parse_choice_row(sheet_name, headers, values, source_row)
            )
            if parsed is None:
                continue
            if candidate_store is not None:
                candidate_store.append({
                    **asdict(parsed),
                    "entity_type": "cue" if is_cue_sheet else "choice",
                })
            if is_cue_sheet:
                identity = (parsed.scene_id, parsed.key, parsed.start, parsed.end)
                current = cue_store.get(identity)
                if current is None or cue_priority.get(sheet_name, 9) < cue_priority.get(
                    str(current["source_sheet"]), 9
                ):
                    cue_store[identity] = asdict(parsed)
            else:
                identity = (parsed.scene_id, parsed.key)
                current = choice_store.get(identity)
                if current is None or choice_priority.get(sheet_name, 9) < choice_priority.get(
                    str(current["source_sheet"]), 9
                ):
                    choice_store[identity] = asdict(parsed)


def _checklist_cases(sheet_name: str, rows: list[list[Any]]) -> list[dict[str, Any]]:
    for header_index, row in enumerate(rows):
        labels = [str(value or "").strip().casefold() for value in row]
        scene_column = next(
            (index for index, label in enumerate(labels) if "scene node" in label), None
        )
        if scene_column is None:
            continue
        result_column = next(
            (index for index, label in enumerate(labels) if "final result" in label), None
        )
        choice_column = next(
            (
                index
                for index, label in enumerate(labels)
                if "choice" in label or "ช้อย" in label or "ชื่อช้อย" in label
            ),
            None,
        )
        cases: list[dict[str, Any]] = []
        for source_row, record in enumerate(
            rows[header_index + 1 :], start=header_index + 2
        ):
            scene_id = str(record[scene_column] or "").strip() if scene_column < len(record) else ""
            normalized_scene_id = " ".join(scene_id.casefold().split())
            if (
                not scene_id
                or scene_id.startswith("#")
                or "total" in normalized_scene_id
                # Master checklists repeat their column header before each group.
                # Treating that label as a scene created dozens of bogus cases
                # with the same ID and unstable source-row provenance.
                or "scene node" in normalized_scene_id
                or normalized_scene_id in {"scene", "ชื่อซีน"}
            ):
                continue
            values = {
                str(row[index] or f"column_{index + 1}"): (
                    record[index] if index < len(record) else None
                )
                for index in range(len(row))
            }
            result = (
                record[result_column]
                if result_column is not None and result_column < len(record)
                else ""
            )
            choice = (
                str(record[choice_column] or "").strip()
                if choice_column is not None and choice_column < len(record)
                else ""
            )
            case_id = f"{sheet_name}:{scene_id}"
            if choice:
                case_id = f"{case_id}:choice:{choice}"
            cases.append(
                {
                    "case_id": case_id,
                    "scene_id": scene_id,
                    "group": sheet_name,
                    "final_result": str(result or "").strip(),
                    "source_sheet": sheet_name,
                    "source_row": source_row,
                    "source_record": _json_value(values),
                }
            )
        return cases
    return []


def _write_index(
    root: Path, profile: str, game_name: str, database: QADatabase, archive: Path
) -> None:
    sheets = database.list_source_sheets(profile)
    memory = database.list_game_memory(profile)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Source workbook index — {game_name}",
        "",
        f"Profile: `{profile}`",
        "",
        "Read-only copies are stored in the per-game SQLite database and JSON archives.",
        "The source Google Sheets are never modified.",
        "",
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sheet in sheets:
        grouped.setdefault(sheet["source_id"], []).append(sheet)
    for source_id, workbook_sheets in grouped.items():
        memory_key = (
            f"source.document.{source_id.removeprefix('doc-')}"
            if source_id.startswith("doc-")
            else f"source.workbook.{source_id}"
        )
        item = next((item for item in memory if item["memory_key"] == memory_key), None)
        source_url = item["source"] if item else ""
        lines.extend(
            [
                f"## Source `{source_id}`",
                "",
                f"Source: {source_url or workbook_sheets[0]['source_name']}",
                "",
                "| Sheet | Data rows | Columns | Links |",
                "|---|---:|---:|---:|",
            ]
        )
        for sheet in workbook_sheets:
            link_count = len(sheet["hyperlinks"])
            lines.append(
                f"| {sheet['sheet_name']} | {sheet['row_count']} | "
                f"{sheet['column_count']} | {link_count} |"
            )
        for sheet in workbook_sheets:
            if not sheet["hyperlinks"]:
                continue
            lines.extend(["", f"### Links in {sheet['sheet_name']}", ""])
            for link in sheet["hyperlinks"]:
                label = link["label"] or link["cell"]
                lines.append(f"- [{label}]({link['target']}) — `{link['cell']}`")
        lines.append("")
    archive_dir = root / "data" / "qa_profiles" / "sources"
    lines.extend(
        [
            f"Raw JSON snapshots: `{archive_dir}`",
            "",
            f"Game memory: `reports/game-memory-{profile}.md`",
            "",
        ]
    )
    (reports / f"source-workbooks-{profile}.md").write_text("\n".join(lines), encoding="utf-8")

    memory_lines = [
        f"# Game memory — {game_name}",
        "",
        f"Profile: `{profile}`",
        "",
        "Memory is isolated per game profile and is available to MCP agents.",
        "",
        "| Key | Category | Confidence | Source | Value |",
        "|---|---|---:|---|---|",
    ]
    for item in memory:
        value = item["value"]
        if item["category"] == "source_document" and isinstance(value, dict):
            value = {
                "name": value.get("name", ""),
                "line_count": len(str(value.get("text", "")).splitlines()),
                "source_url": value.get("source_url", ""),
            }
        compact = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        compact = compact.replace("|", "\\|").replace("\n", " ")
        source = str(item["source"]).replace("|", "\\|")
        memory_lines.append(
            f"| `{item['memory_key']}` | {item['category']} | "
            f"{item['confidence']:.2f} | {source} | {compact} |"
        )
    (reports / f"game-memory-{profile}.md").write_text(
        "\n".join(memory_lines) + "\n", encoding="utf-8"
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
