# Historical Sprint Plan: OCR Tuning & Per-Game Visual Assertions

> This file records an earlier OCR-focused sprint proposal. The current project-wide
> development sequence is in [`docs/roadmap-autonomous-game-qa.md`](docs/roadmap-autonomous-game-qa.md).

## Overview
- **Goal**: Tune OCR engine for game text recognition; add per-game OCR + color assertions derived from live captured evidence
- **Context**: Three Steam demos (SHINEBRINGERS 4077460, Agent Veil 4307180, Unforgettable Love 4511140) pass color assertions on D:\SteamLibrary; Tesseract 5.4 installed at `C:\Program Files\Tesseract-OCR`
- **Quality Gates**: ruff, ruff format, mypy, pytest (via `C:\Python314\python.exe`), pre-commit

---

## Files to Change

### 1. `app/vision/ocr.py` — OCR Engine Enhancements
**New/Modified Functions & Classes:**

```python
# NEW: Preprocessing pipeline for game UI text
def preprocess_for_ocr(frame: np.ndarray, mode: str = "ui") -> np.ndarray: ...

# NEW: Tesseract config builder per use-case
def build_tesseract_config(psm: int = 7, oem: int = 3, whitelist: str | None = None) -> str: ...

# MODIFIED: OCREngine.__init__ — add tesseract_cmd default from env/known path
def __init__(self, tesseract_cmd: str | None = None, config: str = "") -> None: ...

# MODIFIED: OCREngine.read — accept config override
def read(self, frame: np.ndarray, config: str = "") -> str: ...

# MODIFIED: OCREngine.read_words — accept config override
def read_words(self, frame: np.ndarray, config: str = "") -> list[OCRWord]: ...

# NEW: OCRWord.confidence_threshold class attribute for filtering
# NEW: OCREngine.set_preprocessing(mode: str) — chainable config
```

### 2. `app/vision/__init__.py` — Export New Symbols
```python
from app.vision.ocr import OCREngine, OCRWord, preprocess_for_ocr, build_tesseract_config
```

### 3. `qa_framework/gameplay/assertions.py` — Enhanced OCR Assertion
**Modified Function:**
```python
# MODIFIED: _ocr_contains — support region, preprocessing, config, case sensitivity
def _ocr_contains(
    self,
    name: str,
    config: dict[str, Any],
    frame: np.ndarray,
) -> AssertionResult: ...
```

**New Assertion Types (add to `_run_one` dispatch):**
- `ocr_word_present` — exact word match with confidence threshold
- `ocr_region_contains` — OCR within a specific screen rectangle
- `color_region_detected` — color detection constrained to a region

**Config Keys Added:**
```json
{
  "check": "ocr_contains|ocr_word_present|ocr_region_contains|color_region_detected",
  "text": "Play",                    // ocr_contains, ocr_word_present
  "region": [x, y, w, h],            // ocr_region_contains, color_region_detected
  "preprocessing": "ui|raw|binary",  // ocr_* — "ui" default
  "psm": 7,                          // ocr_* — Tesseract page segmentation mode
  "whitelist": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", // ocr_*
  "confidence_threshold": 0.7,       // ocr_word_present
  "color": [b, g, r],                // color_region_detected
  "tolerance": 30,                   // color_region_detected
}
```

### 4. `qa_framework/gameplay/suite.py` — Region Path Resolution
**Modify `_config_from_dict`:**
- Resolve `region` values from relative coords to absolute if needed (no change needed, regions are inline)
- Add validation for new assertion config keys

### 5. `qa_framework/examples/` — Per-Game Suite Files (Evidence-Based)
Create/Update based on captured screenshots from live runs:

| File | Purpose |
|------|---------|
| `game_4077460_shinebringers_ocr.json` | SHINEBRINGERS OCR assertions (menu text, HUD) |
| `game_4307180_agentveil_ocr.json` | Agent Veil OCR assertions |
| `game_4511140_unforgettable_love_ocr.json` | Unforgettable Love OCR assertions |
| `gameplay_combined_ocr.json` | Combined suite referencing the above |

**Example `game_4077460_shinebringers_ocr.json`:**
```json
{
  "timeout": 60.0,
  "capture_delay": 3.0,
  "executable_name": "SwishAndFlick/Binaries/Win64/SwishAndFlickDemo.exe",
  "monitor_index": 1,
  "screenshot_dir": "screenshots/live/ocr",
  "assertions": [
    {
      "name": "main menu 'PLAY' button",
      "check": "ocr_word_present",
      "text": "PLAY",
      "region": [600, 400, 200, 80],
      "preprocessing": "ui",
      "confidence_threshold": 0.6
    },
    {
      "name": "settings 'GRAPHICS' tab",
      "check": "ocr_region_contains",
      "text": "GRAPHICS",
      "region": [100, 100, 400, 100],
      "psm": 6
    },
    {
      "name": "health bar red region",
      "check": "color_region_detected",
      "color": [30, 30, 200],
      "region": [50, 50, 300, 30],
      "tolerance": 40
    }
  ]
}
```

### 6. `tests/vision/test_ocr.py` — Extended Unit Tests
**New Test Cases:**
```python
def test_preprocess_for_ocr_ui_mode() -> None: ...
def test_preprocess_for_ocr_binary_mode() -> None: ...
def test_build_tesseract_config_defaults() -> None: ...
def test_build_tesseract_config_custom_whitelist() -> None: ...
def test_ocr_engine_read_with_custom_config() -> None: ...
def test_ocr_engine_read_words_with_custom_config() -> None: ...
def test_ocr_word_confidence_filtering() -> None: ...
```

### 7. `tests/qa_framework/test_assertions.py` — Assertion Engine Tests
**New Test Cases:**
```python
def test_ocr_word_present_passes_on_match() -> None: ...
def test_ocr_word_present_fails_below_confidence() -> None: ...
def test_ocr_region_contains_crops_correctly() -> None: ...
def test_color_region_detected_constrains_to_region() -> None: ...
def test_ocr_contains_respects_preprocessing() -> None: ...
def test_assertion_engine_dispatch_new_types() -> None: ...
```

### 8. `tests/qa_framework/test_gameplay.py` — Integration Tests
**New Test Cases:**
```python
def test_runner_executes_ocr_assertions(tmp_path: Path) -> None: ...
def test_runner_executes_color_region_assertions(tmp_path: Path) -> None: ...
def test_load_run_config_validates_new_assertion_keys(tmp_path: Path) -> None: ...
```

---

## Acceptance Criteria

### Code Quality (Must Pass)
- [ ] `C:\Python314\python.exe -m ruff check .` — zero errors
- [ ] `C:\Python314\python.exe -m ruff format . --check` — zero diffs
- [ ] `C:\Python314\python.exe -m mypy qa_framework app` — zero errors
- [ ] `C:\Python314\python.exe -m pytest tests/ -v` — all tests pass
- [ ] `pre-commit run --all-files` — zero failures

### Functional
- [ ] `OCREngine` default `tesseract_cmd` resolves to `C:\Program Files\Tesseract-OCR\tesseract.exe` on Windows
- [ ] `preprocess_for_ocr(frame, "ui")` improves text detection on typical game UI (tested against captured frames)
- [ ] `ocr_word_present` assertion passes only when word exists with confidence ≥ threshold
- [ ] `ocr_region_contains` crops frame to region before OCR
- [ ] `color_region_detected` constrains color detection to region
- [ ] All three live game suites pass with their new OCR/color assertions

---

## Step-by-Step Live Verification Procedure

### Phase 1: Capture Evidence Screenshots
```bash
# Run current combined suite to get fresh screenshots
C:\Python314\python.exe scripts/live_gameplay_combined.py
# Screenshots saved to screenshots/live/qa_<app_id>.png
```

### Phase 2: Analyze & Annotate
1. Open each screenshot in an image editor (Paint.NET, GIMP)
2. Identify stable UI text regions (main menu buttons, HUD elements, settings labels)
3. Record pixel-perfect regions `[x, y, w, h]` for each text element
4. Sample BGR colors for health bars, mana, cooldowns, highlight colors
5. Note Tesseract PSM that works best (7=single line, 6=block, 8=single word)

### Phase 3: Write Per-Game OCR Suites
Create JSON files in `qa_framework/examples/` with assertions derived from Phase 2.

### Phase 4: Run Combined OCR Suite
```bash
C:\Python314\python.exe -m qa_framework.gameplay.coordinator run_combined_suite \
  qa_framework/examples/gameplay_combined_ocr.json \
  --output-dir reports/live_ocr
```

### Phase 5: Verify Reports
1. Open `reports/live_ocr/gameplay_report.html`
2. Confirm all three games show PASS with green assertions
3. Check screenshot thumbnails match expected regions
4. If any FAIL: adjust region, preprocessing, PSM, confidence threshold; re-run

### Phase 6: Regression Gate
```bash
# Full test suite must pass before merge
C:\Python314\python.exe -m pytest tests/ -x -q
C:\Python314\python.exe -m ruff check . && C:\Python314\python.exe -m ruff format . --check
C:\Python314\python.exe -m mypy qa_framework app
```

---

## Implementation Order (Dependency-Aware)

1. **OCR Engine Core** (`app/vision/ocr.py`) — no dependencies
2. **Vision Exports** (`app/vision/__init__.py`) — depends on #1
3. **Assertion Engine** (`qa_framework/gameplay/assertions.py`) — depends on #1, #2
4. **Suite Loader** (`qa_framework/gameplay/suite.py`) — depends on #3 (validation)
5. **Unit Tests** (`tests/vision/test_ocr.py`, `tests/qa_framework/test_assertions.py`) — depends on #1-3
6. **Integration Tests** (`tests/qa_framework/test_gameplay.py`) — depends on #3-5
7. **Per-Game Suite JSONs** (`qa_framework/examples/*_ocr.json`) — depends on live evidence
8. **Combined Suite JSON** (`qa_framework/examples/gameplay_combined_ocr.json`) — depends on #7
9. **Live Verification** — run Phase 1-6 procedure

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Tesseract not found on CI | `OCREngine` defaults to Windows install path; gracefully degrades |
| OCR flaky on game UI | Configurable preprocessing + PSM + whitelist per assertion |
| Region coords wrong on different resolutions | Document monitor_index + capture_delay; regions relative to captured frame |
| Color detection false positives | `color_region_detected` constrains search; tolerance tuning per game |

---

## Deliverables Checklist

- [ ] `app/vision/ocr.py` enhanced
- [ ] `app/vision/__init__.py` updated
- [ ] `qa_framework/gameplay/assertions.py` enhanced
- [ ] `qa_framework/gameplay/suite.py` validation added
- [ ] `tests/vision/test_ocr.py` extended
- [ ] `tests/qa_framework/test_assertions.py` created
- [ ] `tests/qa_framework/test_gameplay.py` extended
- [ ] 4 new suite JSONs in `qa_framework/examples/`
- [ ] `NEXT_SPRINT_PLAN.md` this document
- [ ] All quality gates pass
- [ ] Live verification report showing 3/3 games PASS with OCR assertions
