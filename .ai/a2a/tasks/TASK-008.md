# TASK-008: Stronger state signature + param defaults + loop guard

## Goal
Fix weaknesses observed in live run v3.

## Observed problems (from .ai/a2a/live_run_v3.log and skill_trace.jsonl)
1. State signature degenerates to "1.0.0.00000" because only the version string is reliably OCR'd — different menu screens with same version string collide in the cache.
2. VLM returns `key_press` with empty params `{}` — ActionExecutor silently defaults to "space", hiding the issue.
3. Agent can loop forever repeating the same action on an unchanged screen.

## Changes
1. **Signature** (`qa_framework/gameplay_agent/skill_cache.py`): change `signature()` to include frame content, not just OCR words: new method `signature(ocr_words, frame=None)` where if a numpy frame is given, append a coarse visual hash: downscale frame to 16x16 grayscale, quantize each pixel to 2 bits per channel (>>6), flatten to hex string. Combine: ocr-sorted-words + "|" + visual hash prefix (first 32 hex chars).
2. **Loop guard** in live script: keep deque of last 4 actions; if all identical AND frame visual hash unchanged across those steps → inject a variation: replace action with mouse_move to window center + click once, log "loop detected, injecting variation". Also hard-stop after `--max-steps`.
3. **Param defaults**: in normalize step of live script, if action==key_press and no key param → set key="enter" explicitly and log warning (instead of silent space default).
4. Tests (tests/test_skill_cache.py): visual-hash signature differs for different frames, same for same frame; combined signature stable ordering.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent scripts/live_gameplay_agent.py tests/test_skill_cache.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_skill_cache.py tests/test_vlm_agent.py -q
```

## Report
End with `## A2A REPORT`.
