---
description: Run a bounded autonomous gameplay QA session and retain reusable gameplay experience.
agent: fmv-qa-orchestrator
---

Orchestrate a bounded High School Blood Demo QA session using the gameplay agent, then inspect and package results for the QA team.

## Request

Use `$ARGUMENTS` as the optional step budget. The default profile is `highschoolblood-demo` and the default limit is 60 steps. Never turn a bounded session into an unlimited run. Reject profile names that are not present in `scripts/game_profiles.json`. Every request re-selects profile + categories/case IDs via `describe_qa_selection` then `start_qa_campaign`; never reuse a prior selection. Code fixes go through Hermes `delegate_code_task` (OpenCode CLI); gameplay frames stay on the VLM.

## Workflow

1. Read `scripts/game_profiles.json`, the testcase snapshot, `docs/fmv-harness-orchestration.md`, and the matching test suite. Confirm the profile targets the Demo (`steam_app_id` 5173380), and record installed/observed game version and environment before input.
2. Require a visible, targetable `High School Blood [ Demo ]` window. If an EULA, age gate, privacy prompt, login, or permission dialog appears, stop and ask the user to handle it. Never accept agreements or enter credentials.
3. Check that a VLM endpoint and model are configured and reachable. If they are not, do not start the live controller; report the missing prerequisite. OpenCode/Hermes orchestrates; the VLM gameplay agent controls frames. Do not substitute a code-writing model in the per-frame control loop.
4. Run preflight first: `python scripts/fmv_harness.py --profile highschoolblood-demo --steps <budget>`. If it returns blockers, report them and stop. Do not pass `--eula-cleared` unless the user explicitly confirms they accepted the EULA themselves.
5. Only after an unblocked preflight and explicit EULA confirmation, run `python scripts/fmv_harness.py --profile highschoolblood-demo --steps <budget> --execute --eula-cleared`. Keep one bounded agent instance and preserve F12 as the emergency stop.
6. Inspect the immutable per-run `reports/fmv_harness/<run-id>/` manifest, trace, logs and session report. Separate visual change, story progress, and assertion-backed QA status. A changed frame is not proof of correctness.
7. Package requirement-to-case links, case results, repro steps, and evidence references using the run-result contract in `docs/fmv-harness-orchestration.md`. Keep failures and blocked cases; never reset saves, edit original testcase/localization sources, or overwrite evidence to make a run look successful.
8. Ask for a human decision only at consequential/ambiguous story choices, unexpected EULA/privacy/settings prompts, missing test expectations, or repeated inability to progress after bounded recovery. Batch such questions at a checkpoint when safe; do not guess branches or overwrite saves.

## Safety and learning

- The gameplay model is the configured OpenAI-compatible VLM; OpenCode/Hermes orchestrates a QA session and reviews its artifacts. ChatGPT/Codex owns the plan, approval gates, and report review. Do not use a coding agent as a per-frame controller.
- The skill cache is lightweight outcome-weighted behavior memory, not neural-network training or proof that a game passed QA.
- Do not claim model training. Record the distinction between automatic cache reuse, observed game progression, and assertion-backed pass/fail.
- Do not edit game profiles, QA suites, source workbooks, saves, or skill memory without a clear request. Do not commit or push changes.
