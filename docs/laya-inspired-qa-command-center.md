# Laya-Inspired QA Command Center

## Reference distinction

The supplied Laya links describe two different projects. `aayushch/laya` is a local-first multi-persona command center with event intake, staged action cards, approval/dismissal, workflow execution, and analytics. `convaiinnovations/laya` on Hugging Face is a typed text-decision model; it is not a visual game agent or a QA runner. UGAF borrows the command-center workflow pattern, not Laya's identity or code. The Hugging Face model is an optional future classifier candidate only after a Thai/English QA-specific evaluation; it must not control gameplay or issue PASS decisions.

## Current MVP

- The **QA Command Center** tab uses a local JSON action-card store under `reports/qa_command_center/`; no external account connector or cloud database is required.
- A reviewer can approve or dismiss preflight recommendations. A decision only records the review; it never launches a game action.
- **Run safe preflight** calls the existing bounded Harness profile for High School Blood Demo and turns blockers into review cards.
- **Start supervised smoke test** is disabled until the preflight passes and the user personally checks the EULA-cleared confirmation. It starts only the configured bounded run; the Harness rechecks profile, executable, window, VLM endpoint and EULA flag before gameplay input.
- Each run creates a Harness manifest/report path. Results remain UNASSERTED unless deterministic assertions and evidence support a case result.
- Existing OpenCode specialists and the Hermes project skill remain the multi-persona reasoning layer; the desktop UI does not pretend to have called them unless the campaign was run there.

## Adapted architecture

```text
Patch note / testcase / localization / run event
                    ↓
       Local intake + source references
                    ↓
 OpenCode/Hermes QA personas (draft findings)
                    ↓
       Local QA Action Cards (proposed)
                    ↓
    Human approve / dismiss / correct
                    ↓
 Bounded Harness + deterministic assertions
                    ↓
 Evidence audit → report → reviewer sign-off
                    ↘ reviewed corrections → opt-in learning set
```

Unlike Laya's notification sources, UGAF currently has no automatic Google Drive/Steam event connectors. Intake is limited to local run artifacts and manually supplied inputs. Original Google Sheets and save files remain read-only. The current command center does not import or sync source sheets automatically.

## Learning policy

Store reviewer corrections as versioned feedback, separate from raw gameplay traces. Promote a correction to reusable automation only after it maps to a stable testcase/state, has a reproducible precondition and outcome, and passes held-out regression. Do not treat clicks, visual change, VLM confidence, or an unreviewed reward as training labels. Keep actual weight fine-tuning as a separately versioned opt-in pipeline.

## Next delivery stages

1. Add read-only importers for patch-note documents, testcase workbooks, and localization keyed exports; record source hash/revision and conflicts.
2. Add campaign card types for requirement impact, uncovered cases, localization gaps, and evidence requests; invoke OpenCode/Hermes through an explicit plan-only action.
3. Add a unified campaign database and action audit log (SQLite) with user, timestamp, approve/dismiss reason, run IDs, and immutable source/evidence references.
4. Add deterministic assertion plugins for scene IDs, OCR/localization keys, black/frozen frames, video timing, branch routes, and optional audio capture.
5. Add opt-in local decision scoring only after a benchmark; keep the VLM for visual observation and keep human approval at legal prompts, ambiguous branches, and subjective audio/language/content calls.

## Verification boundary

Unit tests verify local card persistence and that gameplay controls remain disabled before required gates. They do not establish that the game build, VLM, screen capture, audio route, or EULA state is ready. A successful preflight is still not a test pass.

References: [Laya command center repository](https://github.com/aayushch/laya) · [Laya typed-decision model card](https://huggingface.co/convaiinnovations/laya)
