# UGAF Game QA Orchestra

The QA Orchestra adds an accountable specialist review chain to the existing game profile, testcase, preflight, and evidence harness. It is configured for project OpenCode and Hermes Agent; neither integration writes to source-of-truth Google Sheets or silently runs a game.

## Team design

| Role | OpenCode ID | Handoff |
|---|---|---|
| QA Intake & Build Control | `specialists/qa-intake` | Game/build identity, source revisions, scope, blockers |
| Test Design & Coverage | `specialists/test-design` | Traceable cases, coverage gaps, expected-result questions |
| Localization QA | `specialists/localization-qa` | Missing/conflicting keys, locale and timing risks, human review |
| FMV Playback & Branch QA | `specialists/fmv-playback-qa` | Scene state graph, choices, seek/timeline/restart risks |
| Visual & UI QA | `specialists/visual-qa` | Measurable visual assertions and review-only concerns |
| Audio & A/V Sync QA | `specialists/audio-qa` | Audio/sync tests, thresholds, human listening gates |
| Automation & Harness Engineer | `specialists/automation-engineer` | Adapter, assertion, timeout, retry, fixture, evidence plan |
| Evidence & Defect Auditor | `specialists/evidence-auditor` | Independent result/evidence consistency audit |
| Release Gate & Handoff | `specialists/release-coordinator` | Coverage summary, open risks, decision sufficiency |

Specialists are OpenCode subagents with edits, shell execution, and nested delegation denied. They analyze supplied documents and evidence; they do not attest to live results. Hermes uses the same role briefs as scoped delegation prompts. The primary `fmv-qa-orchestrator` owns sequencing and synthesis. ChatGPT/Codex remains the independent supervisor/release reviewer.

## Start a campaign

First check setup without opening a game. The runtime check verifies installed CLI versions, the registered OpenCode agents, and the Hermes project skill; it does not ask a model to run a campaign:

```powershell
python scripts/validate_qa_team.py --check-runtime
opencode agent list
hermes skills list
```

OpenCode:

```text
/qa-campaign High School Blood Demo, review the current approved testcase and identify the next safe QA work. Do not execute gameplay.
```

Hermes from the repository:

```powershell
hermes skills trust C:\Users\Admin\UGAFStudio
.\scripts\qa-orchestra.ps1 -Runtime Hermes -Request "Review the High School Blood Demo cases and produce an automation plan. Do not execute gameplay."
```

The one-time Hermes trust command enables this repository's skill; review project skills before trusting. The wrapper validates the team and does not pass `--yolo`. To use OpenCode through the wrapper:

```powershell
.\scripts\qa-orchestra.ps1 -Runtime OpenCode -Request "Plan a Demo smoke run; do not execute gameplay."
```

OpenCode's CLI and in-app slash command both route to `fmv-qa-orchestrator`. If a provider, server, or subagent capability is unavailable, the campaign must report it; do not claim delegated roles ran. Hermes `delegate_task` workers receive fresh contexts, so always pass the exact file paths, build/scope, full question, safety constraints, and expected output in each goal.

## Lifecycle and gates

`intake → parallel specialist analysis → case/traceability design → automation-readiness review → optional supervised run → evidence audit → release handoff`

Campaign attempts are durable and idempotent. To rerun a terminal attempt,
inspect the campaign/run evidence, then use MCP `retry_qa_campaign` with a new
`retry_key` and fresh input/EULA confirmations. Reusing the same key returns
the prior attempt without starting another worker; each attempt and linked run
remain in history. A `RECOVERY_REQUIRED` campaign needs process inspection
before retry because the worker identity could not be verified.

Analysis and case design do not require live game execution. A live run requires an explicit supervised-run request, correct profile/build, clean preflight, bounded steps, and the user's confirmation that they personally handled EULA/age/privacy prompts. Never automate agreement acceptance, credentials, destructive save actions, purchases, or unspecified choices. Stop on unknown UI/state or exceeded recovery budget. Exactly one adapter controls game input.

Status vocabulary is `PASS`, `FAIL`, `BLOCKED`, `NEEDS_REVIEW`, `NOT_RUN`, and `NOT_IN_BUILD`. Only assertion-backed, build-matched cases with required evidence may be PASS. Human review remains mandatory for language correctness, subjective visual/audio quality, lip-sync within unspecified tolerance, and sensitive-content adequacy.

Campaign artifacts belong in a unique `reports/qa_campaigns/<campaign-id>/` directory. A live Harness run is immutable under `reports/fmv_harness/<run-id>/`. Never overwrite raw trace/evidence or source documents. Missing run artifacts remain missing; do not manufacture results. The release specialist reports evidence sufficiency against explicit criteria and never makes an unapproved product decision.

## Setup validation

`qa_framework/orchestration/specialists.json` is the role/output contract. Run `python scripts/validate_qa_team.py` after changing a role. The validator checks role IDs, definitions, OpenCode/Hermes entry points, and required input/output fields. `--check-runtime` only reads local CLI versions; it does not start either agent server or a game.
