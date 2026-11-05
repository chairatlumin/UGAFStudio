# QA Workbench + standalone exe

## What it is

- **QA Workbench** tab in the desktop app (or `python main.py --qa-workbench` /
  `UGAF-QA.exe --qa-workbench` for a workbench-first window).
- The **Story / Patch Note** tab shows the local story timeline and lets you add
  a dev update with version, build ID, category, note, and optional scene IDs.
- Import the supplied Demo Patch/Dev Update sheet from that tab. Imports are
  saved in the local per-game database; the Google Sheet stays read-only.
- Fresh **profile + categories/cases + max steps** selection every run.
- Bounded VLM-driven play, live stdout/stderr, **auto DOCX export** on completion.
- Status stays **UNASSERTED** unless stored assertions support otherwise.

## Run prerequisites (not bundled)

- The game install for the chosen profile (paths in `scripts/game_profiles.json`).
- A local VLM endpoint (`VLM_BASE_URL`, default `http://127.0.0.1:1234/v1`) and
  model (`VLM_MODEL`, default `qwen/qwen2.5-vl-7b`).
- The exe bundles Python + Qt; nothing else to install. No signing/installer.

## Build the exe

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_qa_exe.ps1
# -> dist/UGAF-QA/UGAF-QA.exe (one-directory)
```

Build a side-by-side candidate without overwriting the active package:

```powershell
.\scripts\build_qa_exe.ps1 -OutputDirectory 'dist\UGAF-QA-Next'
```

Existing mutable data inside the selected package folder is preserved. Source
reports are not copied into a new package by default; pass
`-IncludeSourceReports` when a local package should also contain repository
reports. This avoids duplicating large run/evidence folders into release builds.

The build also has a Windows Desktop shortcut named **UGAF QA Workbench**.

Reports/DBs are written **beside the exe** (`reports/`, `data/`), never into
the PyInstaller temp dir. Frozen worker children dispatch internally via
`UGAF-QA.exe --qa-worker scripts.<fmv_harness|live_gameplay_agent>`; source
installs keep using `python scripts/...` unchanged.

## Launch a run from OpenCode / Hermes (existing MCP config)

`opencode.json` already points at `scripts/ugaf_mcp.py`. Per session:

1. `list_game_profiles` — pick a profile explicitly.
2. `describe_qa_selection` with that profile — pick categories/case IDs.
3. `start_live_session` (or `start_qa_campaign`) with explicit
   `profile`, `case_ids`/`categories`, `max_steps`, `confirm_gameplay_input=true`,
   and `confirm_eula_cleared=true` only after the user personally cleared an
   EULA-gated profile. Unattended mode must never auto-accept these.
4. `export_testcase_report_docx` with the finished `run_id`.
5. Feedback: draft only, via `record_qa_feedback`; never fabricate PASS or edit
   source website data.
