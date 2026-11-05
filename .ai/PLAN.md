# UGAF Studio QA — Codex Plan

## Review decision

Current Hermes implementation is AUTO-APPROVED WITH FOLLOW-UPS. No critical gate was found. Continue without routine approval pauses.

## Next objective

Make Steam gameplay QA production-safe for the user's D:\SteamLibrary and prepare the first supervised live run.

## Work sequence

1. Harden process I/O and cleanup in qa_framework/gameplay/launcher.py and runner.py.
2. Add configurable steam_root propagation from suite JSON through coordinator, controller, and GUI.
3. Make executable discovery recursive and report the exact executable selected.
4. Add regression tests for pipe handling, custom Steam root, nested executable discovery, and cleanup failures.
5. Run one supervised live smoke test for each selected game:
   - SHINEBRINGERS Demo — 4077460
   - Agent Veil Demo — 4307180
   - Unforgettable Love — 4511140
6. Tune per-game OCR/color assertions from captured evidence.
7. Generate one combined HTML report and complete a second Codex review.

## Stop conditions

Stop and request user direction only for credential exposure, destructive data loss, security boundary bypass, unrecoverable process cleanup, or scope expansion.

## Active handoff

Read .ai/TASKS/gameplay-qa-hardening.md and implement it on branch hermes/gameplay-qa-hardening.
## Current status after live verification

The gameplay testcase flow is now runnable end-to-end through `qa_framework.gameplay_cli`.
The combined live suite for SHINEBRINGERS Demo, Agent Veil Demo, and Unforgettable Love passed all three assertions and left zero game processes after cleanup.

## Hermes next task

All quality gates passed (ruff, mypy, pytest, compileall). The suite.py regression tests (6 tests) and scripted QA test cases from disk are verified - users can create/modify testcases from JSON without touching Python. The `run_suite_file()` controller method end-to-end works. OCR remains unverified (Tesseract not installed); live suites use color assertions as before.

Follow-ups: consider OCR tuning once Tesseract is available, and validate color thresholds against sharper in-menu screenshots. The scripted QA test cases from disk feature is now complete and production-ready.
