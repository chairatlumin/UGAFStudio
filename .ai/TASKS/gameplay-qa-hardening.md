# Active Task: Gameplay QA Hardening

## Goal

Harden the Steam gameplay QA workflow and make it reliable for the user's
custom Steam library at `D:\\SteamLibrary`.

## Priority order

### P0 — process safety

- Prevent game stdout/stderr pipe backpressure from blocking a launched game.
- Keep guaranteed cleanup on every launch, capture, assertion, and report path.
- Add regression tests for the cleanup and output-handling behavior.

### P1 — actual Steam environment

- Allow `steam_root` to be configured in the JSON suite and passed through the
  controller/GUI.
- Support executable discovery below the install root when a game stores its
  executable in a subdirectory.
- Report ambiguous or missing executables with actionable paths.

### P2 — live visual QA

- Run one supervised live test for each selected game.
- Tune startup timeout, executable name, OCR text, and color thresholds from
  captured evidence.
- Keep unverified assertions as explicit failures, never silent passes.

## Acceptance

- `python -m compileall -q app qa_framework tests` passes.
- Existing tests remain green.
- CLI and GUI can use `D:\\SteamLibrary` without code changes.
- No launched process remains after any failure path.
- A real report includes screenshot, assertion result, cleanup status, and the
  exact executable used.

## Handoff

Work on `hermes/gameplay-qa-hardening`. Read `.ai/AUTO_REVIEW_POLICY.md`.
Non-critical findings are auto-approved; stop only for a critical gate.
Update `.ai/RESULT.md` with commands and exact results.
