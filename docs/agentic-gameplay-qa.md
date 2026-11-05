# Agentic Gameplay QA with OpenCode and Hermes

UGAF separates high-frequency gameplay control from QA orchestration:

1. **OpenCode/Hermes** selects a configured game profile, starts one bounded run, then reviews the trace and report.
2. **The gameplay VLM** observes captured frames and OCR text and returns a constrained action. `LiveGameplayAgent` applies input bounds, capture-health checks, stuck recovery, and the F12 stop key.
3. **The skill cache** remembers state/action pairs by profile and reuses or ranks actions using observed outcomes. Cache files and JSONL traces remain local under `.ai/a2a/`.
4. **QA assertions/testcases** provide pass/fail evidence. A visual frame change is only a weak progression signal; it is not a test pass.

## Use from OpenCode/Hermes

Open `.opencode/commands/gameplay-qa.md` and invoke `/gameplay-qa` with a profile name and optional step budget. The game must already be open and its window title must match `scripts/game_profiles.json`.

For direct runs, use:

```powershell
python scripts/live_gameplay_agent.py --profile <profile-name> --max-steps 60
```

The runtime uses the configured OpenAI-compatible VLM endpoint (`--base-url`, `--model`) and is Windows-only for live window capture/input. Keep runs bounded; press F12 to stop. Start with a small step count before increasing it.

## Adding a game

Add an entry to `scripts/game_profiles.json` with a unique profile key, exact `window_title`, `game_type`, `strategy`, and relevant `menu_keywords`. Use an existing strategy (`menu_nav`, `vn_advance`, or `realtime_flick`) only when its behavior matches the game. Add a reusable declarative suite under `qa_framework/examples/` for deterministic checks. Avoid hard-coding one game's assumptions into shared action/capture code.

## What “learning” means today

The current cache is online, per-profile behavioral memory. It stores an action for an OCR/visual state and uses frame-difference feedback to rank/reuse previous actions. This does not update VLM weights, understand semantic success, or generalize reliably to unseen games. To train model weights, the project still needs curated labeled screenshots/actions, a selected trainable model, a training pipeline, and held-out evaluation. Until then, use assertion-backed QA outcomes and human review for high-impact choices.

## Human intervention policy

Let the agent handle ordinary navigation and bounded recovery. Bring a person in only for unresolved screens, ambiguous expected results, consequential/irreversible choices, or assertion failures requiring a product decision. Keep the game profile, test suite, and source-of-truth localization under human review; traces and cache memory are generated artifacts and should not be mistaken for authoritative test data.
