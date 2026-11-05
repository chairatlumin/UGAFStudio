---
name: game-qa-orchestra
description: Orchestrate evidence-based game QA with specialist reviewers, deterministic test design, a bounded UGAF Harness, and a clear Dev/QA handoff.
version: 1.0.0
---

# UGAF Game QA Orchestra

Use this skill for game QA planning, testcase design, automation readiness, supervised gameplay runs, or release handoff in UGAFStudio. Hermes is the workflow orchestrator; OpenCode specialists provide focused reviews; ChatGPT/Codex is the supervisor and final evidence/release reviewer. Hermes delegates do not share chat history, so every task must include its full context, exact input paths, profile/build, scope, safety rules, and requested response structure.

## Start safely

1. Confirm the repository and read `AGENTS.md`, `docs/fmv-harness-orchestration.md`, `qa_framework/orchestration/specialists.json`, the requested profile, and only the source files needed for the task.
2. Validate the local team with `python scripts/validate_qa_team.py`. If this fails, stop and report the missing role/entry point.
3. Create one unique campaign directory under `reports/qa_campaigns/`. Source Google Docs/Sheets, localization exports, saves, and prior evidence are read-only.
4. Confirm game identity, app ID, actual build ID, version, patch-note target, testcase revision, locales/platforms, test data, and in-scope features. Never confuse app ID with build ID. A mismatch means BLOCKED, not PASS.

## Specialist delegation

Use `delegate_task` for independent, read-only specialist work. Pass the delegate a complete goal and context because workers start without the parent conversation. Run these roles in parallel for intake/design: **QA Intake & Build Control** (identity/scope), **Test Design & Coverage** (case quality), **Localization QA** (key/locale risks), **FMV Playback & Branch QA** (state graph), **Visual & UI QA** (layout/frame assertions), and **Audio & A/V Sync QA** (audio checks). Then request **Automation & Harness Engineer** to assess the approved test design. After execution, request **Evidence & Defect Auditor**; only then ask **Release Gate & Handoff** to synthesize. Use the role prompts in `.opencode/agents/specialists/` as the role briefs. The role roster and outputs are defined in `qa_framework/orchestration/specialists.json`.

Each delegated goal must name the role, campaign, relevant file paths, selected profile/build, scope, exact requested output, and the rule to label unsupported facts UNKNOWN. In the synthesis, identify the actual completed delegates; do not present one model's self-review as independent specialist review. If delegation is unavailable, do a sequential checklist and disclose that limitation.

## Live gameplay gates

- First run only the non-interactive preflight: `python scripts/fmv_harness.py --profile highschoolblood-demo --steps 10`.
- Do not launch or control a game unless the user requested a supervised gameplay run, EULA/age/privacy gates were personally handled by the user, the matching profile/build is confirmed, preflight is clear, and a bounded step budget is approved.
- Never accept agreements, enter credentials, select an unspecified story branch, reset/delete/overwrite saves, purchase, or modify source/testcase data. Stop on unknown UI, prompts, unexpected state, capture loss, or exhausted recovery budget.
- Use only one game-input controller. Let FMV video play passively unless an approved case authorizes an action. Do not use frame change, VLM confidence, or cache reward as a QA pass.
- Every PASS requires a stable case ID, matching build, expected-vs-observed result, deterministic assertion, and required evidence. Unknown results remain BLOCKED, NEEDS_REVIEW, or NOT_RUN.

## Local QA MCP tools

When the `ugafstudio-qa` MCP server is connected, use `list_game_profiles`,
then `describe_qa_selection(profile)` for every new request to show the
profile's game genre, testcase categories, and cases. Never silently reuse a
previous selection. Start a bounded campaign with explicit `profile` and
`categories` and/or `case_ids` via `start_qa_campaign`, only after the gameplay
and EULA gates above are satisfied. Create new cases only when the user asks,
using `create_testcase`; this writes a local DRAFT overlay and never edits the
read-only website. Each game's story data, runs, results, and reviewed feedback
are stored in `data/qa_profiles/qa_<profile>.sqlite3`. Use `list_live_runs`,
`stop_live_session`, `get_story_database_summary`, `list_database_runs`,
`get_testcase_report`, and `record_qa_feedback` to review evidence. Call
`export_testcase_report_docx(run_id, profile)` to create an editable Word report
with testcase results and evidence paths under `reports/qa_reports/`.

For an explicit code-change request, call `delegate_code_task` with the full
task and constraints. This hands implementation to the local OpenCode CLI and
returns its result. Do not use it for gameplay, which is controlled by the VLM.
OpenCode must never call `delegate_code_task` recursively. A visually guided
testcase run remains UNASSERTED until deterministic assertions and evidence are
reviewed; never report it as PASS based on the model's narrative.

## Handoff

Write `campaign_plan.md`, `specialist_findings.md`, `traceability.csv` when cases exist, and `handoff.md` under the unique campaign folder. Include source references and revisions, test run ID/build, coverage and status totals, failures/blocks, evidence links, reproducible steps, open owners, known limitations, and human decisions. Link Harness run files rather than copying or rewriting raw evidence. Explicitly state whether gameplay ran and whether evidence is sufficient for release review. Return the campaign path to ChatGPT/Codex for independent review.
