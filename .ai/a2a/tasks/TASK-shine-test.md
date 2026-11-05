# TASK-shine-test: Shinebringer Demo 4077460 QA Suite

## Goal
Create and run a comprehensive QA test suite for Shinebringer Demo (App ID 4077460) using the existing qa_framework. Tests should cover:

1. **Steam install QA** — install dir exists, exe present
2. **Launch smoke** — game launches, renders non-black frame, no crash
3. **Menu detection** — menu screen detected via color
4. **Gameplay showcase** — Play button click → game starts (existing `game_4077460_shinebringers_live.json`)
5. **Visual regression** — capture before/after key states

## Context
- Repo: `C:/Users/Admin/UGAFStudio`
- Steam root: `D:\SteamLibrary`
- Game exe: `SwishAndFlick/Binaries/Win64/SwishAndFlickDemo.exe`
- Window title: `SHINEBRINGERS`
- Strategy: `realtime_flick`
- OCR min conf: 40
- Existing suite: `qa_framework/examples/game_4077460_shinebringers_live.json` (launch + color detect [70,67,65] tolerance 45)
- Existing tests: `qa_framework/tests/` (currently empty, add new tests here)
- Existing report: `reports/live/gameplay_report_20260904_105103.html` (PASS)
- Product gate: `reports/product-gate_shinebringer_20260904.md`

### Test framework
- `qa_framework/suite.py` — JSON-based declarative QA suites
- `qa_framework/steam_qa.py` — Steam install verification
- `qa_framework/gameplay_cli.py` — gameplay QA runner
- `app/qa/test_case.py` — TestCase / TestRunner / TestResult
- Check types: `file_exists`, `directory_exists`, `executable_count`, `color_detected`, `ocr_contains`, `template_match`, `engine_version_supported`

### Game info
- Demo showcase flow: Day1 → Night1 → Day2 → Night2 → Day3 → Night3 → Day4 (7 stages)
- Menu click: Play button (coordinate fragile, use polling if possible)
- Wave counts matter (Wolf was +1 before as known bug)
- Known holds: Night3 monster stuck, Day2/Night1 map clip, FPS drop Night2/Graveyard

## Constraints
- Python 3.14 (`C:/Python314/python.exe`)
- `PYTHONPATH=C:/Users/Admin/UGAFStudio`
- Use ruff + type hints
- No new heavy dependencies
- Reuse existing framework (don't build new tools)
- Tests must be deterministic (mock external calls where possible)
- Run actual game tests only if game is installed; otherwise create test scaffolding

## Acceptance criteria
```bash
cd C:/Users/Admin/UGAFStudio
# Unit tests for QA suite logic
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest qa_framework/tests/test_shinebringer.py -q
# Lint
PYTHONPATH=C:/Users/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/tests/test_shinebringer.py
# If game installed, run live QA
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m qa_framework.steam_qa --app-id 4077460 --steam-root D:\SteamLibrary
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m qa_framework.gameplay_cli --suite qa_framework/examples/game_4077460_shinebringers_live.json --app-id 4077460 --steam-root D:\SteamLibrary --output-dir reports/live
```

## Deliverables
1. `qa_framework/tests/test_shinebringer.py` — unit tests for:
   - Steam install assertions (mock filesystem)
   - Suite JSON loading and validation
   - Color detection logic (mock cv2)
   - Wave count verification logic
   - Test result reporting
2. `qa_framework/examples/shinebringer_qa_suite.json` — declarative suite covering:
   - Install verification
   - Launch + render detection
   - Menu color detection
   - (Optional) showcase stage progression
3. `reports/qa_shinebringer_plan.md` — brief test plan document
4. Run the actual live QA if game installed

## Report
End with `## A2A REPORT` listing:
- Files created/modified
- Test output (pytest results)
- Whether live QA was attempted and result
- Any bugs found or known holds encountered
