# Game memory and source sheet sync

Studio Framework keeps a read-only snapshot of each linked Google Sheet or Doc in
the selected game's SQLite profile. Each profile is isolated under
`data/qa_profiles/`; raw snapshots are also archived under
`data/qa_profiles/sources/`. Refreshing a source replaces its saved sheet snapshot
and refreshes the generated index in `reports/`. It does not write to Google.

## HighSchoolBlood sources

The built-in **อัปเดตทุกชีตและเอกสารที่เชื่อมกับเกมนี้** action syncs these sources:

| Profile | Source | Imported content |
|---|---|---|
| `highschoolblood-demo` | [Demo workbook](https://docs.google.com/spreadsheets/d/1O330dlrm8_6G4N9CXxzoYhTbT-DIluwPp1Vu6z4M0tA/edit) | All tabs, flow/checklist data and linked source references |
| `highschoolblood-demo` | [Demo flow workbook](https://docs.google.com/spreadsheets/d/1YgM62LkVJzsdqQmRqOnDDzA-927QoYzLrue4QGw-Mww/edit) | All tabs and flow data |
| `highschoolblood-demo` | [Demo patch notes](https://docs.google.com/document/d/1xUEw3M7H5F4_bgO_bjlT0JbsLRDnItNVdxL5XCCQYb8/edit) | Full document text |
| `highschoolblood-full` | [Full game workbook](https://docs.google.com/spreadsheets/d/1ohPVHfDdJWKfWMRSH445erC4y1cRgFfE/edit) | All tabs, flow/checklist data and linked source references |
| `highschoolblood-full` | [Localization workbook](https://docs.google.com/spreadsheets/d/1b_N7FjwOKSOphXd5m0w-XxfeZcESebjnxFd4aX_Gzfk/edit) | All tabs, subtitle cues and choice localization |
| `highschoolblood-full` | [Minigame documentation](https://docs.google.com/document/d/1uIkg7y2AoZMvWAZbvG9b2uMw-k7Gf1j8wQXf7Z2GML4/edit) | Full document text and minigame requirements |

The demo workbook also links to a Figma board. Its URL is preserved in the source
snapshot; Figma content is not fetched by the Google Sheet importer.

## Refresh and inspect

1. Open **Studio Framework → Source Sheets / Memory**.
2. Select the game profile and use **อัปเดตทุกชีตและเอกสารที่เชื่อมกับเกมนี้**.
3. For another Google Sheet or Doc, paste its read-access URL and choose
   **นำเข้าข้อมูลทั้งหมด**.
4. Review the generated `reports/source-workbooks-<profile>.md` index and archived
   JSON before using inferred flow links as an automation oracle. The complete raw
   source rows are preserved for comparison. The readable memory mirror is
   `reports/game-memory-<profile>.md`.

The importer retains every worksheet row and hyperlink. It also extracts scene
IDs, testcase checklist rows, subtitle cues, choice strings and minigame text when
their source layout matches known headers. Flow edges inferred from adjacent
spreadsheet columns are candidate edges, not verified gameplay results. Game
memory records the source URLs, tab inventory, import counts and known QA rules;
manual memory can be added from the same page.

## Obsidian vault and full-text search

Use **สร้าง / อัปเดต Obsidian Vault ของเกมนี้** on the same page to export a
profile-scoped Markdown vault. The default location is
`data/qa_profiles/vaults/<profile>/Home.md`; folders include Sources, Scenes,
Requirements, Memory, Testcases, Runs and Defects. Page names use stable IDs and
frontmatter carries profile, revision/build, confidence and source citation data.
Flow, subtitle and choice pages link to source pages and Excel row numbers where
the importer has that provenance. Run, testcase and feedback pages link back to
their related records.

SQLite remains canonical. The vault is a generated, read-only projection and
never writes Markdown edits to a Google Sheet or back into SQLite. The exporter
tracks only the Markdown files it generated so removed database entities can be
removed from a later export without touching unrelated files in the vault.

Current exports are available at `data/qa_profiles/vaults/highschoolblood-demo`
and `data/qa_profiles/vaults/highschoolblood-full`. The 2026-10-11 source refresh
created three revisions per profile (two workbooks plus the patch-note document).
The Full workbook has four localization conflict groups preserved for review.

The **ค้น Memory** field uses SQLite FTS5 within the selected game's database.
It indexes game facts, current source rows, current story, testcases, QA runs and
run-linked feedback. Results include a snippet and source/build/run citation.
OpenCode/Hermes can call MCP `search_game_memory` and `export_game_vault`; the
existing `get_game_memory` remains available for structured facts. Search is
full-text, not semantic/vector search, and profile databases are not combined.

Known HighSchoolBlood rules recorded in memory include the pre-game language
selection, the Visual Choice setting, and the Go Left choice set with four visible
options plus its timeout behavior. Verify these against the latest source sheet
when the game changes.

## Agent access

OpenCode uses the repository's `ugafstudio-qa` MCP entry in `opencode.json`. The
MCP server exposes `get_game_memory`, `list_source_sheets`, and `read_source_sheet`
for an agent to retrieve the selected game's saved context. Configure Hermes to
launch `scripts/ugaf_mcp.py` as a local MCP server if that Hermes installation
supports MCP stdio servers; Hermes integration is not automatically active just
because OpenCode is configured.

## Limits

This source sync needs the signed-in/readable Google export URLs to remain
accessible. It does not edit the website or source sheets. Figma and any links
inside Docs/Sheets are retained as references rather than recursively downloaded.
Visual analysis workflows require a running ComfyUI server and compatible models;
source sync and game memory do not depend on ComfyUI.
