"""Deterministic Obsidian-compatible projection and FTS search for game profiles."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.database.database import QADatabase, sanitize_profile_key


def _page_id(kind: str, key: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", key).strip("-_").lower()[:48] or "item"
    digest = hashlib.sha256(f"{kind}\0{key}".encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}"


def _frontmatter(metadata: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        lines.append(f"{key}: {encoded}")
    lines.extend(["---", ""])
    return "\n".join(lines)


def _cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).replace("|", "\\|").replace("\n", " ")


def _has_content(values: Any) -> bool:
    if not isinstance(values, (list, tuple)):
        values = [values]
    return any(value is not None and str(value).strip() for value in values)


def _write_page(root: Path, folder: str, filename: str, metadata: dict[str, Any], body: str) -> Path:
    target = root / folder / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_frontmatter(metadata) + body.rstrip() + "\n", encoding="utf-8")
    return target


def _active_citations(database: QADatabase, profile: str) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (item["entity_type"], item["entity_key"]): {
            "source_id": item["source_id"],
            "sheet": item["sheet_name"],
            "row": item["row_number"],
            "revision_hash": item["revision_hash"],
        }
        for item in database.list_source_entity_provenance(profile, status="active")
    }


def _documents(database: QADatabase, profile: str) -> list[dict[str, Any]]:
    """Build profile-only search docs whose citations point back into the SQLite source of truth."""
    docs: list[dict[str, Any]] = []
    citations = _active_citations(database, profile)
    for item in database.list_game_memory(profile):
        docs.append({
            "entity_type": "memory",
            "entity_id": item["memory_key"],
            "title": item["memory_key"],
            "body": f"{item['category']} {json.dumps(item['value'], ensure_ascii=False)}",
            "citation": {"source": item["source"], "confidence": item["confidence"]},
        })

    for sheet in database.list_source_sheets(profile):
        revision = str(sheet.get("revision_hash") or "")
        if not revision:
            continue
        for row in database.list_source_revision_rows(
            profile, sheet["source_id"], revision, sheet_name=sheet["sheet_name"]
        ):
            if not _has_content(row["payload"]):
                continue
            body = json.dumps(row["payload"], ensure_ascii=False, sort_keys=True)
            docs.append({
                "entity_type": "source_row",
                "entity_id": f"{sheet['source_id']}:{sheet['sheet_name']}:{row['row_number']}",
                "title": f"{sheet['source_name']} / {sheet['sheet_name']} row {row['row_number']}",
                "body": body,
                "citation": {
                    "source_id": sheet["source_id"], "source_url": sheet["source_url"],
                    "sheet": sheet["sheet_name"], "row": row["row_number"],
                    "revision_hash": revision,
                },
            })

    project = database.load_story_project(profile)
    if project:
        for scene_id, scene in project["scenes"].items():
            content = [scene_id, scene.get("group", "")]
            content.extend(
                str(text) for cue in scene.get("cues", [])
                for text in cue.get("translations", {}).values()
            )
            content.extend(
                str(text) for choice in scene.get("choices", [])
                for text in choice.get("translations", {}).values()
            )
            content.extend(
                f"{link.get('choice_key', '')} {link.get('target', '')}"
                for link in scene.get("outgoing", [])
            )
            docs.append({
                "entity_type": "scene", "entity_id": scene_id, "title": scene_id,
                "body": " ".join(content),
                "citation": citations.get(("scene", scene_id), {}),
            })

    for case_id, case in database.list_testcase_sources(profile).items():
        docs.append({
            "entity_type": "testcase", "entity_id": case_id, "title": case_id,
            "body": json.dumps(case, ensure_ascii=False, sort_keys=True),
            "citation": {
                "source_sheet": case.get("source_sheet", ""),
                "source_row": case.get("source_row"),
                **citations.get(("testcase", case_id), {}),
            },
        })

    for run in database.list_runs(profile=profile, limit=200):
        result_text = []
        for result in database.list_testcase_results(run["run_id"]):
            result_text.append(
                " ".join((
                    result["case_id"], result["status"], result["observed"],
                    json.dumps(result["expected"], ensure_ascii=False),
                    json.dumps(result["assertions"], ensure_ascii=False),
                    json.dumps(result["evidence"], ensure_ascii=False),
                ))
            )
        docs.append({
            "entity_type": "run", "entity_id": run["run_id"], "title": run["run_id"],
            "body": " ".join(str(run.get(key, "")) for key in (
                "build_id", "status", "qa_status", "started_at_utc", "report_path"
            )) + " " + " ".join(result_text),
            "citation": {
                "manifest_path": run.get("manifest_path", ""),
                "trace_path": run.get("trace_path", ""),
                "report_path": run.get("report_path", ""),
                "build_id": run.get("build_id", ""),
            },
        })

    with database._connect() as connection:  # noqa: SLF001 - read-only profile-scoped index projection
        feedback = connection.execute(
            """SELECT f.* FROM qa_feedback AS f JOIN qa_runs AS r ON r.run_id = f.run_id
               WHERE r.profile = ? ORDER BY f.created_at_utc, f.feedback_id""",
            (profile,),
        ).fetchall()
    for item in feedback:
        body = f"{item['category']} {item['note']} case={item['case_id']} run={item['run_id']}"
        docs.append({
            "entity_type": "defect", "entity_id": item["feedback_id"],
            "title": item["category"], "body": body,
            "citation": {"run_id": item["run_id"], "case_id": item["case_id"]},
        })
    return docs


def search_game_memory(
    database: QADatabase, profile: str, query: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Refresh the derived profile index and return FTS snippets with citations."""
    if not query.strip():
        return []
    docs = _documents(database, profile)
    database.replace_game_memory_search_index(profile, docs)
    return database.search_game_memory(profile, query, limit)


def export_game_vault(database: QADatabase, profile: str, destination: Path | None = None) -> dict[str, Any]:
    """Create deterministic Markdown pages; edits to these files never sync back into SQLite."""
    game = next(
        (item for item in database.list_games() if item["profile"] == profile),
        {"display_name": profile, "game_type": "unknown"},
    )
    root = Path(destination) if destination is not None else (
        database.path.parent / "vaults" / sanitize_profile_key(profile)
    )
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / ".ugaf-generated.json"
    try:
        old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        old_manifest = {"files": []}
    generated_files: set[str] = set()

    def write(folder: str, filename: str, metadata: dict[str, Any], body: str) -> Path:
        path = _write_page(root, folder, filename, metadata, body)
        generated_files.add(path.relative_to(root).as_posix())
        return path

    citations = _active_citations(database, profile)
    pages: dict[str, list[tuple[str, str]]] = {
        folder: [] for folder in (
            "Sources", "Scenes", "Requirements", "Memory", "Testcases", "Runs", "Defects"
        )
    }

    sheets = database.list_source_sheets(profile)
    source_page_refs: dict[tuple[str, str], tuple[str, str]] = {}
    for sheet in sheets:
        revision = str(sheet.get("revision_hash") or "")
        rows = database.list_source_revision_rows(
            profile, sheet["source_id"], revision, sheet_name=sheet["sheet_name"]
        ) if revision else []
        rows = [item for item in rows if _has_content(item["payload"])]
        page = _page_id("source", f"{sheet['source_id']}:{sheet['sheet_name']}")
        lines = [
            f"# {sheet['source_name']} / {sheet['sheet_name']}", "",
            f"Source: {sheet.get('source_url', '')}", f"Revision: `{revision}`", "",
            "| Row | Content |", "| ---: | --- |",
        ]
        lines.extend(f"| {item['row_number']} | `{_cell(item['payload'])}` |" for item in rows)
        if sheet["hyperlinks"]:
            lines.extend(["", "## Hyperlinks", ""])
            lines.extend(
                f"- [{item['label'] or item['cell']}]({item['target']}) · `{item['cell']}`"
                for item in sheet["hyperlinks"]
            )
        rel = f"Sources/{page}.md"
        source_page_refs[(str(sheet["source_id"]), str(sheet["sheet_name"]))] = (
            page, str(sheet["sheet_name"])
        )
        write("Sources", f"{page}.md", {
            "id": f"source:{sheet['source_id']}:{sheet['sheet_name']}",
            "profile": profile, "source_id": sheet["source_id"],
            "sheet": sheet["sheet_name"], "revision_hash": revision,
            "source_url": sheet.get("source_url", ""), "read_only_projection": True,
        }, "\n".join(lines))
        pages["Sources"].append((rel, sheet["sheet_name"]))

    project = database.load_story_project(profile)
    scene_links: dict[str, str] = {}
    if project:
        for scene_id, scene in project["scenes"].items():
            page = _page_id("scene", scene_id)
            scene_links[scene_id] = page
            lines = [f"# {scene_id}", "", f"Group: {scene.get('group', '')}", ""]
            links = scene.get("outgoing", [])
            if links:
                lines.extend(["## Flow", ""])
                lines.extend(
                    f"- [[{scene_links.get(link['target'], _page_id('scene', link['target']))}|"
                    f"{link['target']}]] · choice `{link.get('choice_key', '')}`"
                    for link in links
                )
                lines.append("")
            for title, field in (("Subtitle cues", "cues"), ("Choices", "choices")):
                if scene.get(field):
                    lines.extend([f"## {title}", ""])
                    for entry in scene[field]:
                        if field == "cues":
                            source_entity_key = json.dumps(
                                [scene_id, entry.get("key", ""),
                                 float(entry.get("start", 0)), float(entry.get("end", 0))],
                                ensure_ascii=False, sort_keys=True,
                            )
                            entity_type = "cue"
                        else:
                            source_entity_key = json.dumps(
                                [scene_id, entry.get("key", "")], ensure_ascii=False,
                                sort_keys=True,
                            )
                            entity_type = "choice"
                        cue_citation = citations.get((entity_type, source_entity_key), {})
                        source_ref = source_page_refs.get((
                            str(cue_citation.get("source_id", "")),
                            str(cue_citation.get("sheet", "")),
                        ))
                        row_suffix = (
                            f" · [[{source_ref[0]}|{source_ref[1]}]]!{cue_citation['row']}"
                            if source_ref and cue_citation.get("row") else ""
                        )
                        lines.append(
                            f"- `{entry.get('key', '')}`: "
                            + "; ".join(
                                f"{locale}={text}" for locale, text in
                                sorted(entry.get("translations", {}).items())
                            ) + row_suffix
                        )
                    lines.append("")
            citation = citations.get(("scene", scene_id), {})
            source_ref = source_page_refs.get((
                str(citation.get("source_id", "")), str(citation.get("sheet", ""))
            ))
            if source_ref and citation.get("row"):
                lines.extend([
                    f"Source: [[{source_ref[0]}|{source_ref[1]}]]!{citation['row']}", ""
                ])
            write("Scenes", f"{page}.md", {
                "id": f"scene:{scene_id}", "profile": profile,
                "source_id": citation.get("source_id", ""),
                "source_sheet": citation.get("sheet", ""),
                "source_row": citation.get("row"),
                "revision_hash": citation.get("revision_hash", ""),
            }, "\n".join(lines))
            pages["Scenes"].append((f"Scenes/{page}.md", scene_id))

    for memory in database.list_game_memory(profile):
        is_requirement = memory["category"] in {"user_requirement", "requirement"}
        folder = "Requirements" if is_requirement else "Memory"
        page = _page_id("memory", memory["memory_key"])
        body = (
            f"# {memory['memory_key']}\n\nCategory: `{memory['category']}`\n\n"
            f"Source: {memory['source']}\n\n"
            f"Confidence: {memory['confidence']}\n\n"
            f"```json\n{json.dumps(memory['value'], ensure_ascii=False, indent=2, sort_keys=True)}\n```"
        )
        write(folder, f"{page}.md", {
            "id": f"memory:{memory['memory_key']}", "profile": profile,
            "category": memory["category"], "source": memory["source"],
            "confidence": memory["confidence"], "review_status": "unreviewed",
        }, body)
        pages[folder].append((f"{folder}/{page}.md", memory["memory_key"]))

    for case_id, case in database.list_testcase_sources(profile).items():
        page = _page_id("testcase", case_id)
        scene_id = str(case.get("scene_id", ""))
        scene_link = f"[[{scene_links.get(scene_id, _page_id('scene', scene_id))}|{scene_id}]]" if scene_id else ""
        citation = citations.get(("testcase", case_id), {})
        source_ref = source_page_refs.get((
            str(citation.get("source_id", "")),
            str(citation.get("sheet", case.get("source_sheet", ""))),
        ))
        source_link = (
            f"[[{source_ref[0]}|{source_ref[1]}]]!{citation.get('row', case.get('source_row', ''))}"
            if source_ref else f"{case.get('source_sheet', '')}!{case.get('source_row', '')}"
        )
        body = (
            f"# {case_id}\n\nScene: {scene_link}\n\n"
            f"Source citation: {source_link}\n\n"
            f"```json\n{json.dumps(case, ensure_ascii=False, indent=2, sort_keys=True)}\n```"
        )
        write("Testcases", f"{page}.md", {
            "id": f"testcase:{case_id}", "profile": profile,
            "scene_id": scene_id, "source_sheet": case.get("source_sheet", ""),
            "source_row": case.get("source_row"),
            "revision_hash": citation.get("revision_hash", ""),
        }, body)
        pages["Testcases"].append((f"Testcases/{page}.md", case_id))

    runs = database.list_runs(profile=profile, limit=200)
    for run in runs:
        page = _page_id("run", run["run_id"])
        lines = [f"# QA run {run['run_id']}", "", f"Build: `{run['build_id']}`",
                 f"Status: `{run['status']}` / QA `{run['qa_status']}`", "",
                 f"Started: {run['started_at_utc']}", "",
                 f"Manifest: `{run['manifest_path']}`", f"Trace: `{run['trace_path']}`",
                 f"Report: `{run['report_path']}`", "", "## Testcase results", ""]
        for result in database.list_testcase_results(run["run_id"]):
            case_page = _page_id("testcase", result["case_id"])
            lines.extend([
                f"- [[{case_page}|{result['case_id']}]] — `{result['status']}`: {result['observed']}",
                f"  - Expected: `{_cell(result['expected'])}`",
                f"  - Assertions: `{_cell(result['assertions'])}`",
                f"  - Evidence: `{_cell(result['evidence'])}`",
            ])
        write("Runs", f"{page}.md", {
            "id": f"run:{run['run_id']}", "profile": profile,
            "build_id": run["build_id"], "status": run["status"],
            "qa_status": run["qa_status"],
        }, "\n".join(lines))
        pages["Runs"].append((f"Runs/{page}.md", run["run_id"]))

    with database._connect() as connection:  # noqa: SLF001 - read-only export of profile-linked feedback
        feedback = connection.execute(
            """SELECT f.* FROM qa_feedback AS f JOIN qa_runs AS r ON r.run_id = f.run_id
               WHERE r.profile = ? ORDER BY f.created_at_utc, f.feedback_id""",
            (profile,),
        ).fetchall()
    for item in feedback:
        page = _page_id("defect", item["feedback_id"])
        run_page = _page_id("run", item["run_id"])
        case_page = _page_id("testcase", item["case_id"]) if item["case_id"] else ""
        body = (
            f"# {item['category']}\n\n{item['note']}\n\n"
            f"Run: [[{run_page}|{item['run_id']}]]\n\n"
            + (f"Testcase: [[{case_page}|{item['case_id']}]]\n" if case_page else "")
        )
        write("Defects", f"{page}.md", {
            "id": f"defect:{item['feedback_id']}", "profile": profile,
            "category": item["category"], "run_id": item["run_id"],
            "case_id": item["case_id"], "review_status": "unreviewed",
        }, body)
        pages["Defects"].append((f"Defects/{page}.md", item["category"]))

    summary = database.story_summary(profile)
    lines = [
        f"# {game['display_name']}", "",
        f"Profile: `{profile}`", f"Game type: `{game['game_type']}`", "",
        "SQLite is the source of truth. This vault is a generated read-only projection; "
        "editing Markdown never writes back to source sheets or the database.", "",
        "## Profile summary", "",
        " | ".join(f"{key}: {summary.get(key, 0)}" for key in (
            "scenes", "subtitles", "choices", "links", "testcases", "evidence", "source_sheets"
        )), "",
    ]
    for folder, entries in pages.items():
        if not entries:
            continue
        lines.extend([f"## {folder}", ""])
        lines.extend(f"- [[{Path(path).stem}|{label}]]" for path, label in sorted(entries))
        lines.append("")
    write("", "Home.md", {
        "id": f"game:{profile}", "profile": profile,
        "game_type": game["game_type"], "read_only_projection": True,
    }, "\n".join(lines))

    root_resolved = root.resolve()
    for relative in set(old_manifest.get("files", [])) - generated_files:
        candidate = (root / relative).resolve()
        if root_resolved not in candidate.parents or candidate.suffix.casefold() != ".md":
            continue
        if candidate.is_file():
            candidate.unlink()
    manifest_path.write_text(
        json.dumps({"profile": profile, "files": sorted(generated_files)}, indent=2),
        encoding="utf-8",
    )
    docs = _documents(database, profile)
    database.replace_game_memory_search_index(profile, docs)
    return {
        "profile": profile, "vault_path": str(root.resolve()),
        "markdown_pages": sum(len(items) for items in pages.values()) + 1,
        "search_documents": len(docs),
    }
