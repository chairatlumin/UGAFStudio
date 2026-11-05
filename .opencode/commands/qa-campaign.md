---
description: Run the multi-specialist QA campaign for a game profile and produce an evidence-backed handoff.
agent: fmv-qa-orchestrator
---

Run the UGAF QA specialist campaign for the request in `$ARGUMENTS`. Read `qa_framework/orchestration/specialists.json` and validate the setup with `python scripts/validate_qa_team.py` before analysis. Work in the current repository and create a unique campaign folder under `reports/qa_campaigns/`; never edit source Google Docs/Sheets or overwrite previous evidence.

## Delegation contract

Delegate to the OpenCode specialists by their exact ids and pass each a self-contained goal, profile/build/scope, source paths, campaign path, and expected output. Parallelize only independent read-only analysis. Use `specialists/qa-intake`, `specialists/test-design`, `specialists/localization-qa`, `specialists/fmv-playback-qa`, `specialists/visual-qa`, and `specialists/audio-qa` for intake/design. After they finish, call `specialists/automation-engineer` using the agreed cases. For an existing run, call `specialists/evidence-auditor`, then `specialists/release-coordinator`. If delegation is unavailable, perform each role as a clearly labeled sequential review and state that no independent subagents ran. Do not claim a role completed if it was not actually invoked.

## Phases and gates

1. **Intake:** confirm exact game/profile/App ID, installed build and in-game version, patch-note target, testcase revision, platform, locales and declared scope. Source docs are read-only. If build identity conflicts, mark affected work BLOCKED.
2. **Specialist review:** return each role's findings with source references, uncertainties, contradictions, and human-review requirements. Do not let specialist suggestions overwrite approved requirements.
3. **Test/automation design:** create requirement→case→assertion→evidence traceability. Keep stable IDs. Cases must have explicit setup, deterministic steps, expected state, stop conditions, priority, automation level, and evidence. Unspecified branches remain questions, not assumed expected results.
4. **Preflight:** for High School Blood Demo use `python scripts/fmv_harness.py --profile highschoolblood-demo --steps 10` first. Never run `--execute` unless the user explicitly requested a supervised gameplay run, personally confirms they handled EULA/age/privacy gates, and preflight has no blockers. Never pass `--eula-cleared` based on inference. Do not reset/delete/overwrite saves. Other profiles also require owner-approved run scope and a bounded budget.
5. **Execution:** at most one input controller per game. No speculative branch choice, agreement acceptance, credential entry, purchases, destructive save actions, or unbounded recovery. Stop on unknown UI, unexpected prompt, capture loss, unresolved branch, or safety boundary. If execution is unauthorized/unavailable, report NOT_RUN or BLOCKED rather than simulating a run.
6. **Audit and handoff:** do not infer PASS from frame change or model narrative. PASS requires a case-linked assertion and required evidence. Preserve FAIL/BLOCKED/NEEDS_REVIEW/NOT_RUN/NOT_IN_BUILD. Record known limitations and owners; ChatGPT/Codex performs final independent review and release decision.

## Campaign artifacts

Create `campaign_plan.md`, `specialist_findings.md`, `traceability.csv` (when cases/requirements are available), and `handoff.md` in the unique campaign folder. If a live Harness run actually occurs, link its immutable `run_manifest.json`, `results.json`, `results.csv`, `evidence/index.json`, `trace.jsonl`, and `report.html`; do not fabricate missing artifacts. `handoff.md` must say what was and was not executed, identify blockers and human decisions, and state whether results are sufficient for a release decision.
