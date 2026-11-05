# TASK-027: Headless OCR-suite validator against saved evidence frames

## Goal
Build a headless validator that runs the existing per-game OCR assertion suites
(`qa_framework/examples/game_4077460_shinebringers_ocr.json`,
`game_4307180_agentveil_ocr.json`, `game_4511140_unforgettable_love_ocr.json`, and
`gameplay_combined_ocr.json`) against the REAL captured screenshots already in
`screenshots/` — reporting which assertions PASS/FAIL and the actual OCR text
found. This de-risks the blocked "live 3/3 OCR PASS" (which needs a foreground
game session) using evidence we already captured.

## Context (file paths)
- `qa_framework/gameplay/assertions.py` — `_validate_assertion`, `run_assertion` /
  the assertion engine. OCR checks: `ocr_contains`, `ocr_word_present`,
  `ocr_region_contains`. Each assertion dict has `name`, `check`, `text`/`region`/
  `color`, optional `psm`/`confidence_threshold`/`preprocessing`.
- `qa_framework/gameplay/suite.py` — `load_runs_config` / `load_run_config` parses
  the JSON suites; each per-game entry has `app_id`, `assertions`, optional
  `executable_name`.
- `app/vision/ocr.py` `OCREngine` (`available()`, `read_words(frame, psm, scale,
  confidence_threshold)`, `read(frame)`). Tesseract is installed at
  `C:\Program Files\Tesseract-OCR\tesseract.exe`.
- Saved evidence frames in `screenshots/` (do NOT modify them):
  - Agent Veil menu frames: `screenshots/av_menu_clean.png`, `av_avg.png`,
    `av_avg2.png`, `av_avg3.png`, `av_menu_01.png`, `av_menu_02.png`,
    `av_menu_zoom.png`, `st28_avg.png`, `st29_avg.png`. Verified OCR: av_menu_clean
    shows "Tutorial"; av_avg shows "Creat[e] Looby" (=Create Lobby).
  - SHINEBRINGERS: `screenshots/swishflow/sw_30.png` (1536x864 "You are Dead /
    Respawn" frame; OCR words Item/Last/Pete/Dead/Respawn per prior RESULT.md).
  - Unforgettable Love: no clean menu frame captured yet — treat as a DRAFT /
    EXPECTED-FAIL and report it as such (do not fabricate a passing result).

## Changes required

### 1. New script `scripts/validate_ocr_suite.py`
A self-contained CLI (no game window, no Steam) that:
- Accepts `--suite <json>` and `--evidence-dir <dir>` (default `screenshots`).
- Loads the suite via `load_run_config` (single-game) or `load_runs_config`
  (combined).
- For each game in the suite, finds candidate evidence PNGs in `evidence-dir`
  (match by `app_id` heuristics: 4077460->swishflow/sw_*.png or any swishflow
  frame; 4307180->av_*.png / st2*.png / st28*.png / st29*.png; 4511140->any ul_*.png
  / love frame — none expected). Use a simple substring/glob match; if no frame
  is found, mark every assertion for that game as SKIPPED (evidence missing).
- For each assertion, run the actual assertion against EACH candidate frame
  using the assertion engine's OCR path (`ocr_contains` / `ocr_word_present` /
  `ocr_region_contains`). Capture pass/fail + the actual OCR words text (joined)
  for the frame.
- Print a clear report (stdout) per game:
  ```
  [4307180] agentveil  evidence=av_menu_clean.png
    PASS  ocr_word_present:Tutorial   ocr="Tutorial | Settings | Exit"
    PASS  ocr_contains:Settings        ocr="..."
    FAIL  ocr_region_contains:Exit     ocr="..."   (region may be wrong)
  ```
  And a final summary line: `SUMMARY: 3 passed, 1 failed, 0 skipped (game 4307180)`.
- Exit code 0 if every game with evidence has >=1 passing assertion and no
  unexpected crash; exit code 2 if any assertion unexpectedly throws. SKIPPED
  (no evidence) does NOT fail the run.

### 2. Tests — `tests/test_validate_ocr_suite.py` (NEW)
Use a tiny generated PNG (draw text with cv2) as a fixture so the test is
self-contained (no dependency on `screenshots/`):
- `test_validator_runs_ocr_assertion_on_generated_frame`: generate a frame with
  the word "START", run a one-assertion suite (`ocr_word_present: START`) against
  it via the new script's core function; assert PASS.
- `test_validator_skips_when_no_evidence`: point evidence-dir at an empty temp
  dir; assert the assertion is reported SKIPPED and exit code is 0.
- `test_validator_reports_failure`: generate a blank frame; assert an
  `ocr_word_present` assertion on a word NOT present is reported FAIL.

Expose the core logic as an importable function (e.g.
`validate_suite(suite_dict, evidence_dir) -> list[dict]`) so the tests call it
directly (not via subprocess).

## Constraints
- Do NOT modify the example `*_ocr.json` suites or `screenshots/`.
- Do NOT launch any game or Steam.
- Reuse the existing assertion engine (do not re-implement OCR).
- All new code must pass: ruff, ruff format, mypy, pytest.

## Exact validation commands (must all pass)
```bat
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/validate_ocr_suite.py tests/test_validate_ocr_suite.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff format --check scripts/validate_ocr_suite.py tests/test_validate_ocr_suite.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m mypy scripts/validate_ocr_suite.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_validate_ocr_suite.py -q
```
Also run it live (evidence exists) and paste the report into the A2A REPORT:
```bat
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/validate_ocr_suite.py --suite qa_framework/examples/game_4307180_agentveil_ocr.json --evidence-dir screenshots
```

## Report format
End with `## A2A REPORT`: files touched, validation outputs, the live OCR
validation report against `screenshots/`, and follow-ups (e.g. which regions need
tuning, Unforgettable Love evidence gap).
