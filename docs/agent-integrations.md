# Hermes and OpenCode integration

UGAF Studio exposes its local QA workflows through one stdio MCP server.
The same tools are available to Hermes and OpenCode: inspect configured games,
read testcases by genre, save local testcase drafts and feedback, run bounded
live sessions, inspect session status, and stop a session. Website content is
read-only; new testcases and feedback are saved under this project only. Story
flow, subtitle cues, testcase snapshots, run records and report links are stored
per game in `data/qa_profiles/qa_<profile>.sqlite3` (shared `data/ugaf_qa.sqlite3`
history is preserved read-only and only that profile's rows are copied on first use).

## OpenCode

The project root `opencode.json` registers the MCP server. Open the repository
as the OpenCode project and run `opencode mcp list`; `ugafstudio-qa` should be
listed as connected. The command uses the local Python 3.14 installation and
the launcher sets the project root as its working directory.

## Hermes

Register the same stdio server once in Hermes:

```powershell
hermes mcp add ugafstudio-qa --command C:\Python314\python.exe --args C:\Users\Admin\UGAFStudio\scripts\ugaf_mcp.py
hermes mcp test ugafstudio-qa
```

The launcher changes to `C:\Users\Admin\UGAFStudio` before starting the
server, so the working directory Hermes inherited does not matter.

## Tool workflow

1. Call `list_game_profiles`, then `describe_qa_selection` for the chosen
   profile to get its available categories and cases. Every campaign/run
   request must pass a fresh explicit `profile` plus selected `categories`
   and/or `case_ids`; selections are never reused silently and case IDs are
   validated against the profile genre.
2. The catalog is a read-only starting point; use `create_testcase` to save
   project-local additions in `qa_framework/testcases/local_cases.json`.
3. Start live play with `start_qa_campaign` (fresh selection, one bounded run)
   or `start_live_session` with explicit `case_ids`/`categories`, only when
   authorized with `confirm_gameplay_input=true`, a bounded `max_steps`
   between 1 and 600, and `confirm_eula_cleared=true` where required. Only one
   session per game profile can run at a time. Keep its returned `run_id`.
4. Code changes are separate from gameplay: Hermes calls `delegate_code_task`
   with an explicit task (local OpenCode CLI, 30-600s timeout, structured
   result). OpenCode must never call `delegate_code_task` (recursion guard);
   the per-frame gameplay controller is always the VLM, never a coding model.
5. Review trace and HTML report evidence, then call `record_qa_feedback` to
   save findings in that game's SQLite file and `reports/qa_feedback.jsonl`.
   Use `get_story_database_summary`, `list_database_runs`, and
   `get_testcase_report` (optional `profile`) to review stored results.
   Hermes can export an editable Word copy with `export_testcase_report_docx`
   (`run_id`, optional `profile`); it returns `docx_path`, `run_status`,
   `qa_status`, and `case_count` for the file under
   `reports/qa_reports/<safe-profile>/testcase_report_<safe-run>.docx`.

6. If a campaign is `INTERRUPTED`, `FAILED`, `BLOCKED`, or `STOPPED`, inspect
   its attempts and evidence first. Then call `retry_qa_campaign` with the
   `campaign_id`, a new stable `retry_key`, bounded `max_steps`, and fresh
   `confirm_gameplay_input=true`; EULA-gated games also require
   `confirm_eula_cleared=true`. Each retry is a new immutable attempt and run
   linked to the same campaign. Reusing a `retry_key` returns that attempt and
   never starts another worker. `RECOVERY_REQUIRED` must be resolved by
   inspecting the saved worker before retrying.

The live agent follows the case steps but does not itself assert PASS. Use the
declarative suite runner and its deterministic assertions for automated
pass/fail; unresolved observations remain review items. For profiles marked
`requires_eula_ack`, the user must handle the
agreement in game and separately confirm `confirm_eula_cleared=true`.
