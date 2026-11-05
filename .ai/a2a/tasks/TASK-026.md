# TASK-026: Capture-health guard (black/frozen/desktop frame detection)

## Goal
Add a capture-health guard to the live gameplay loop so a bad capture
(black frame, frozen/identical-to-previous, or matching the desktop wallpaper)
is detected and surfaced instead of silently driving a meaningless frame into
the VLM / MOA. This addresses the documented failure mode in `.ai/RESULT.md`:
"Windows blocks background PrintWindow/mss capture of a fullscreen D3D window"
— the loop currently proceeds on whatever `grab_frame` returns.

## Context (file paths)
- `scripts/live_gameplay_agent.py`:
  - `grab_frame(hwnd)` (line 86) returns a BGR numpy array via PrintWindow+GetDIBits.
  - `main()` loop calls `grab_frame` at lines ~723 and ~741, feeding frames into
    `live.step(frame, ocr_words, next_frame)`.
  - `LiveGameplayAgent` (line 314) owns the per-step loop logic (`step()`).
- `qa_framework/gameplay_agent/reward.py` `FrameDiffReward` already computes a
  visual hash (`_visual_hash` in `skill_cache.py`) — reuse it for freeze detection.

## Changes required

### 1. New module-level helper in `scripts/live_gameplay_agent.py`
```python
def frame_health(frame: np.ndarray) -> dict[str, float]:
    """Return capture-health metrics for *frame*.

    Keys:
      mean_brightness  - mean of grayscale (0..255); very low => black frame.
      non_black_ratio  - fraction of pixels with max(R,G,B) > 8.
      unique_ratio     - fraction of distinct quantized (4-bit) colors; very low
                         => flat / single-color (wallpaper-like) frame.
    """
```
(Quantize with `>> 4` on each channel; count distinct colors via numpy.unique on
the reshaped array; approximate is fine.)

### 2. `LiveGameplayAgent.__init__` additions
- `self._prev_capture_hash: str | None = None` (reuse `_visual_hash`).
- Accept an optional `capture_warn_threshold: float = 0.02` (min non_black_ratio)
  and `freeze_warn: bool = True` (default True).

### 3. `LiveGameplayAgent.step()` — pre-decision capture-health check
At the very top of `step()` (before OCR/decide), compute `h = frame_health(frame)`:
- If `h["non_black_ratio"] < self._capture_warn_threshold`:
  log a WARNING `"capture health: near-black frame (non_black_ratio=...)"`, set
  `self._last_capture_health = h`, and RETURN early with `reward=0.0` (do NOT
  call the agent, do NOT dispatch, do NOT write a trace entry for this frame) so
  a black/empty capture does not pollute the VLM/MOA or skill cache.
- Else if `freeze_warn` and `_visual_hash(frame) == self._prev_capture_hash`:
  log a WARNING `"capture health: frame unchanged since last step (possible
  capture freeze)"`; do NOT early-return (a legitimately static menu can repeat),
  but record `self._last_capture_health = h` and continue.
- Always update `self._prev_capture_hash = _visual_hash(frame)` and
  `self._last_capture_health = h` at the end of the check.

Add `self._last_capture_health: dict[str, float] | None = None` for observability
(used by tests + future session report).

### 4. Tests — `tests/test_capture_health.py` (NEW)
- `test_frame_health_black`: a zeros frame → non_black_ratio ~0.0, mean_brightness 0.
- `test_frame_health_normal`: a varied random frame → non_black_ratio high (~1.0).
- `test_step_skips_black_frame`: build a `LiveGameplayAgent` with a
  `MagicMock(spec=VLMAgent)` agent + `MagicMock` executor + `SkillCache`; call
  `step(black_frame, [], black_frame)`; assert the agent.decide was NOT called and
  the executor.dispatch was NOT called (Reward/early-return path). Use a non-black
  frame for a second call to confirm it DOES proceed.
- `test_step_freeze_logged_not_skipped`: two identical non-black frames → second
  step still calls agent.decide (freeze is a warning, not a skip).

## Constraints
- Do NOT change `grab_frame` itself.
- Keep all existing strategy branches (menu_nav / realtime_flick / vn_advance) intact.
- All new code must pass: ruff, ruff format, mypy, and the new + existing tests.

## Exact validation commands (must all pass)
```bat
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py tests/test_capture_health.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff format --check scripts/live_gameplay_agent.py tests/test_capture_health.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m mypy scripts/live_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_capture_health.py tests/test_moa_live_wiring.py tests/test_game_profiles.py -q
```

## Report format
End with `## A2A REPORT` listing files touched, validation outputs, follow-ups.
