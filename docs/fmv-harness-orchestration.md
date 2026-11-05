# High School Blood Demo: FMV QA Harness & Orchestration

## Purpose and scope

This is the handoff contract for repeatable QA of **High School Blood Demo only** (Steam app 5173380). The installed full game is not the target. Each run must identify its executable, in-game version, Steam Build ID, locale, display mode/resolution, and testcase revision. Patch-note claims apply only when their target build matches the tested build.

On 2026-09-23 I initially opened the wrong, unfinished full-game debug build. Only on that wrong build did I observe a main menu, four Chapter Select cards, and a chapter/story path map with Back/Main Menu/Continue controls; its visible version was `v0.0.1-DevTest-23`. Those observations are explicitly **not Demo evidence** and must not be used for sign-off. After the correction, I opened the installed Demo executable and observed its first-run EULA; exploration stopped there. No agreement was accepted, and no Demo menu, chapter playback, VLM-driven gameplay, or automated pass/fail run has been verified. The Demo manifest reports app ID `5173380`, Steam Build ID `25325884`, and install size approximately 8.83 GB. Local OpenCode (`127.0.0.1:4096`) and VLM (`127.0.0.1:1234`) endpoints were unavailable at exploration time.

The runtime profile is `highschoolblood-demo`. `scripts/fmv_harness.py` performs a non-interactive preflight and creates a unique manifest directory. Execution requires a targetable Demo window, matching Demo profile, responsive vision model, and the user's explicit confirmation that they handled the EULA. Use `python scripts/fmv_harness.py --profile highschoolblood-demo --steps 60` to preflight; the script does not launch Steam. Only execute after all checks pass and the user confirms the EULA: add `--execute --eula-cleared`. Each run uses a unique trace and HTML report path rather than appending to the shared profile trace.

## Harness roles

| Role | Owner | Responsibility | Must not |
|---|---|---|---|
| Supervisor / QA owner | ChatGPT or Codex | Approves scope and build, generates risk-based plan from patch note/localization/testcases, resolves product questions, reviews evidence and signs off | Claim a pass without evidence; drive frame-by-frame inputs |
| Orchestrator | OpenCode agent `fmv-qa-orchestrator` / Hermes | Checks prerequisites, invokes bounded runners, resumes only from checkpoints, collates artifacts, reports exceptions | Accept legal prompts, choose unspecified story branches, modify source sheets/saves |
| Gameplay policy | Configured vision-language model through the gameplay agent | Interprets the current frame/OCR and proposes one constrained action | Decide QA pass/fail from its own narrative; bypass action safety |
| Action/capture adapter | UGAF `LiveGameplayAgent`, Windows capture/input | Captures the game window, validates capture health, dispatches allowlisted input, records trace, supports F12 stop | Run more than one controller, escape/skip on a passive FMV screen |
| Evaluator | Deterministic assertions + human reviewer where needed | Checks exact expected state, text, timing, media and branch results; assigns status | Convert “screen changed” into PASS |
| Human gate | QA owner / game owner | Handles EULA, ambiguous branches, policy decisions, unobservable audio/content calls, and recovery beyond limits | Edit the source-of-truth testcase sheet during a run |

ChatGPT/Codex and OpenCode/Hermes are supervisory/execution agents, not interchangeable with the VLM. OpenCode commands and project agent files provide reusable orchestration prompts; the Python gameplay runner remains the actual input controller.

## Run from OpenCode/Hermes

The project command `/gameplay-qa [step-budget]` selects the `fmv-qa-orchestrator` agent. It must run preflight first:

```powershell
python scripts/fmv_harness.py --profile highschoolblood-demo --steps 60
```

Only after the user independently handles the EULA and confirms that fact may the orchestrator execute:

```powershell
python scripts/fmv_harness.py --profile highschoolblood-demo --steps 60 --execute --eula-cleared
```

The harness refuses execution if the wrong profile/app is selected, the Demo executable/window is missing, the vision endpoint/model is unavailable, or the EULA acknowledgement is absent. It does not install or launch Steam. OpenCode/Hermes should return the run directory and blockers to the ChatGPT/Codex supervisor for review; no automated pass is inferred from successful process exit.

The older settings-matrix launcher is `scripts/hsb_campaign.ps1`. Each invocation now creates a UTC-stamped campaign directory containing per-step logs and JSON manifests. It stops at the first nonzero harness exit code, and an unknown `-Only` value is rejected. Completion is recorded as `COMPLETED_UNASSERTED`; the launcher does not treat a successful process exit as testcase PASS. `scripts/hsb_flow.py newgame` now refuses to proceed when the Demo save exists, and does not move or overwrite it. The campaign therefore requires a clean/disposable test fixture prepared by the owner; it will not reset an existing save as a side effect. Current operational validation is limited to a failure-injection runner and a no-save mutation unit test; no Demo window was present during that check, so no real campaign was run.

## Imported graph coverage audit

Use the read-only MCP tool `get_fmv_coverage_report(profile="highschoolblood-demo")` to inspect root reachability, disconnected scenes, testcase coverage, unresolved edge labels, and branching options. `export_fmv_coverage_report` writes the same result as a timestamped JSON report and returns its SHA-256. The report keeps source-graph coverage separate from execution: inferred labels are marked `candidate_unverified`, candidate timeouts are not treated as confirmed timer behavior, and execution/QA status stays `NOT_RUN` / `UNASSERTED`.

The current Demo profile needs source reconciliation before this legacy graph can be used for route planning. It contains 603 scene rows and 64 links, but provenance marks only 12 scenes source-active, 591 scene rows are unowned, and none are stale. Ten links connect two active source scenes; 54 links touch an unowned scene. The configured `01_Prescene_S001` root is unowned and reaches zero active source scenes. The four roots in the active source subgraph (`DEmo013`, `SchoolDay_001`, `SchoolDay_005`, `SchoolDay_006`) reach all 12 active scenes, but no evidence establishes that these are the Demo's actual start state. The complete stored graph has 548 weak components, including 545 isolated scene rows; all 64 stored links have blank `choice_key`. The Go Left legacy branch has five target testcase label candidates: Chainsaw, Nail Gun, Shotgun, Buddha Statue, and Choose Nothing. `NoChoice` / Choose Nothing is a **timeout candidate**, not verified timer behavior. The report marks provenance `MISMATCH`, execution `NOT_RUN`, and QA `UNASSERTED`. Snapshot: [fmv_coverage_20261024T181657588096Z.json](../reports/qa_reports/highschoolblood-demo/fmv_coverage_20261024T181657588096Z.json). Resolve the source-row/root mapping and obtain actual Demo evidence before planning branch coverage from these records.

## Existing QA data baseline

These are read-only snapshot figures, not results from the current Demo build:

- Existing testcase snapshot: 409 rows, 408 distinct scene IDs; 220 Pass, 39 Fail, 150 Pending in the saved snapshot. The old status labels are historical and must not be reported as a fresh run.
- Feedback tags in that snapshot: subtitle/localization 132 cases, video transitions 82, choice visibility 37, layout overflow 20, audio quality 16, progression/blockers 14, and lip-sync/timing 2. Use these counts as risk signals, not as mutually exclusive test totals.
- Localization workbook: `Luna Subtitle` has 3,738 cues and two missing English values; `Luna Choice` has 310 records. Legacy/unnamed sheets overlap and differ, so import must retain source-sheet/key and report conflicts rather than silently deciding which text is approved.
- Earlier Dev feedback included missing scream/door-knock voice, a content filter that may leave sensitive imagery too visible, and playback/navigation issues around rapid pause/seek, transition freezes, old ending video after returning to menu, and timeline replay flashing a previous moment. Link each to its original case/scene and retest only against the matching Demo build.

Before signing off, reconcile the patch-note content (`0.0.2-Demo-40`) with the installed Demo manifest. The patch-note field called “Build ID 5173380” matches the Steam **app ID**, whereas the local Steam **Build ID** is `25325884`; ask Dev which exact build the note describes and correct the release metadata in the QA manifest without editing their source document.

## Run lifecycle

1. **Intake** — Read the read-only Patch Note, localization export, existing testcase/report snapshot, target build, and known issues. Record source revisions/hashes. Do not write to the source Google Docs/Sheets.
2. **Impact analysis** — Map patch-note items and defects to existing testcase IDs; identify changed scenes, languages, playback controls, choices, and dependencies. Add cases only for uncovered requirements; preserve original IDs and source references.
3. **Preflight** — Confirm Demo app/build, window title, executable, VLM endpoint/model, display dimensions, capture health, language, required save fixture, and output capacity. Stop on EULA/privacy/age prompts for the user. A build mismatch marks affected tests BLOCKED, not PASS.
4. **Baseline** — Capture initial menu, profile/config versions, save fixture identity (never the save contents), frame/OCR baseline, and runner version. Use a test save or disposable profile where the game supports it; do not reset the user’s save without explicit approval.
5. **Execution** — Run one scenario at a time with explicit preconditions, max steps/time, allowable actions and stop conditions. Prefer deterministic navigation/assertions. Let FMV clips play passively; only act on tested controls or choices whose expected branch is specified. Checkpoint between chapters/branches.
6. **Evaluation** — Use deterministic text/image/timing/audio assertions where possible. Human-review any subjective censorship/content, lip-sync, audio quality, translation nuance, or low-confidence visual result. Every case ends PASS, FAIL, BLOCKED, or NEEDS_REVIEW.
7. **Triage and learning** — Preserve raw traces. Promote an action into reusable memory only when its precondition and outcome are reviewed. Distinguish “observed visual change,” “scene progressed,” and “assertion passed.” Record corrected actions as demonstrations; do not automatically train or bless the policy from unreviewed rewards.
8. **Handoff** — Generate a human-readable HTML/PDF report plus machine-readable JSON/CSV, evidence index, failed/blocked/needs-review IDs, reproduction steps, and owner/action for every unresolved issue. ChatGPT/Codex reviews the package before sharing.

## High School Blood Demo coverage matrix

The source snapshot currently contains **409 testcase rows across 408 distinct scene IDs**. Keep these as the base inventory and calculate coverage by stable testcase ID; do not assume scene count equals test count. Reconcile duplicate/revision localization sheets and keep the chosen sheet/key/source visible in each result.

| Area | Required scenarios | Automation/evidence | Manual gate or edge |
|---|---|---|---|
| Install, startup, version | Correct Demo executable/app ID; cold start; first-run overlay; black/frozen screen; menu ready | Process/window identity, manifest/build, timestamped screenshot, capture-health result | EULA and any first-run agreement require the user; first-run state recorded separately |
| Menu and chapter select | Continue/new game, chapter cards, locked/unlocked state, back/main-menu behavior | OCR/anchor assertion, click trace, before/after screenshots | Verify account/save-dependent chapter availability against a known fixture |
| FMV playback | Start/resume, play/pause, wait, completion, end-of-clip transition, repeat/loop, buffering/freeze | Sampled frame hashes/black-frame detector, playback-time checkpoints, action timeline | Visual/audio defects judged by a reviewer if a robust threshold is unavailable |
| Seeking and timeline | Forward/back seek (including five-second behavior), no accidental choice skip, scrubbed scene identity, replay older timeline point | Before/after timestamp and scene assertion, short clip evidence, seek/action trace | Never seek into unreviewed content during unattended run; branch-dependent timeline reviewed |
| Story path and branching | Current path/checkpoint, locked path, each choice option, branch destination, replay a prior moment, continue/restart behavior | Expected branch graph from approved source, state/scene ID assertion, saved screenshot | Choice policy/expected outcome must be specified; ambiguous branch pauses for QA owner |
| Choices and UI overlays | Choice text/localization, hotspot/hover/held-choice visibility, settings/pause overlay, subtitle interaction | OCR+region assertions, click/hold/release timestamps, screenshots at transition | Subjective overlap/readability reviewed at supported resolutions |
| Localization/subtitles | Thai/English (and every shipped locale), missing key, timing, overlap, punctuation/font/clipping, choice translation | Import keyed cue rows, compare displayed text against approved key, start/end/overlap checks, screenshot/OCR | Linguistic quality and culturally sensitive phrasing require language reviewer |
| Audio/media | Dialogue/SFX/BGM presence and separation, missing lines, clipping, mute/volume behavior, A/V sync | Audio loopback capture where allowed; loudness/silence/onset checks aligned with frame timestamps | Voice acting, scream quality, censor suitability, and subtle sync judged by human |
| Content filter/privacy/external links | Blur/filter state; privacy policy; wishlist link; settings/window mode; overlay behavior | State/UI assertions, link target allowlist (do not submit data), screenshots | External navigation, consent, account and privacy decisions are human gated |
| Stability/recovery | Pause+seek rapid sequence, chapter transitions, back to menu then new game, old-frame flash, rewind/next-video behavior | Bounded repetition, frame freeze/black checks, process liveness, trace, crash log | Long soak/performance requirements need an agreed time/budget and dedicated machine |
| Compatibility | Supported window/fullscreen modes, 16:9/4K and declared ratios, scaling, multi-monitor, controller if supported | Fixed resolution matrix and layout assertions | Hardware/driver combinations not present in CI are marked BLOCKED, not assumed |

For each patch note, add an explicit `requirement_id -> testcase_id(s) -> evidence/assertion -> result` traceability row. Backlog/known issues stay open until a matching build and repeatable passing evidence are attached.

## Test case contract

Minimum case fields for sharing across QA/Dev/Localization:

```json
{
  "case_id": "HBS-FMV-PLAY-001",
  "requirement_id": "REQ-FMV-PLAYBACK",
  "title": "Continue playback without skipping a choice",
  "priority": "P1",
  "automation_level": "automated_with_visual_review",
  "preconditions": ["High School Blood Demo build is recorded", "test save fixture is loaded"],
  "steps": [{"action": "wait", "seconds": 8}, {"action": "observe", "checkpoint": "choice_boundary"}],
  "expected": ["video advances", "choice remains visible until selected or timed out"],
  "assertions": ["scene_id changes only after expected transition", "choice OCR is visible"],
  "data_refs": [{"type": "localization_key", "key": "Scene_2_Day1_c013_000"}],
  "stop_conditions": ["unexpected branch", "black frame > 2 seconds", "capture lost"],
  "evidence_required": ["screenshot_before", "screenshot_after", "action_trace", "video_timecodes"]
}
```

Store game-specific case files under `qa_framework/testcases/` or `qa_framework/examples/` according to the existing runner contract. The example above is a schema illustration, not a verified expected behavior; product/QA must approve its expected result before execution.

## Run-result contract for handoff

One immutable run directory per attempt, named with UTC timestamp and run ID. Include:

- `run_manifest.json`: run ID, game/profile, Steam app ID, **Steam Build ID and in-game version**, executable hash, branch/commit, OS, screen resolution/scale, locale, audio device, VLM provider/model, runner version, suite/testcase revision, patch/localization source revisions, start/end time, and operator.
- `results.json` and `results.csv`: one row per testcase ID with status, requirement link, expected/observed, actual action, assertion details, elapsed time, retry count, defect ID, reviewer, and evidence paths.
- `evidence/index.json`: artifact type, relative path, timestamp/timecode, testcase ID, capture method, and SHA-256. Preserve original media; redact only a separately derived copy when required.
- `trace.jsonl`: per observation/action with UTC timestamp, scene/state signature, OCR text, proposed/executed action, policy/cache source, reward (explicitly labelled heuristic), result status, and recovery/manual intervention.
- `report.html` (and optional PDF): summary, coverage/traceability, PASS/FAIL/BLOCKED/NEEDS_REVIEW counts, defects, known issues, missing evidence, environment mismatch, and reproducible steps.

Do not upload screenshots, videos, audio, logs, save files or user identifiers to an external model/service unless the project owner explicitly approves the specific data and destination. Prefer local processing and reference artifacts by relative path.

## Online memory vs actual model training

`SkillCache` is small per-profile action memory keyed by OCR/visual signature. Current `FrameDiffReward` only says the image changed; it cannot establish that the story advanced correctly. It is suitable for cautious action reuse, not semantic RL or release sign-off. High School Blood Demo uses `fmv_passive` so an unchanged screen will not trigger blind cached alternatives or an automatic Escape action; choices and seeks must be test-authorized.

To train actual model weights later, add a separate opt-in pipeline: capture licensed/local screenshots or clips, pair each with approved state/scene label and action, mark success/failure from assertions/human review, split data by scene/build (no near-duplicate leakage), train a selected trainable model, and compare against the unchanged baseline on held-out scenes. Record model/data versions and rollback criteria. Do not send Steam/user media to a hosted trainer by default.

## Current blockers and next gates

1. User must review/accept the Demo EULA in the game window; automation must not accept it.
2. OpenCode server at `127.0.0.1:4096` was unavailable during initial exploration.
3. VLM endpoint at `127.0.0.1:1234/v1` was unavailable; configure a vision-capable model before the gameplay agent can act.
4. Reconcile the patch-note “Build ID 5173380” field with the local Steam app ID `5173380` and installed Steam Build ID `25325884`; confirm the exact target Demo build with Dev.
5. Establish an approved clean/test save fixture and get the exact supported locale/resolution/controller matrix from Dev/QA.
6. After gates 1–5, run a short supervised smoke, validate evidence capture, then expand through existing 409 cases and branch coverage. Do not run the full suite until save/reset strategy and completion criteria are approved.
