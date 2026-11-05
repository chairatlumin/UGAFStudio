# TASK-006: Harden live_gameplay_agent — PrintWindow capture, param normalization, OCR grounding

## Goal
Fix three known issues in `scripts/live_gameplay_agent.py` so the loop is robust for long runs.

## Changes
1. **PrintWindow capture** (replace mss grab): implement `grab_frame(hwnd)` using user32.PrintWindow(hwnd, memdc, PW_RENDERFULLCONTENT=2) + GetDIBits, exactly as in `.ai/a2a/capture_printwindow.py` (copy the logic into the script; keep mss import removed). This captures the game window even when other windows overlap it.
2. **Param normalization**: VLMAgent may return params like `{"key_name": "enter"}` or `{"key": "enter"}`. Add a normalize step before dispatch:
   - map `key_name`→`key`, `text` stays `text`.
   - Whitelist allowed keys: w,a,s,d,space,enter,escape,tab,e,q,shift. Any key outside whitelist → replace action with `noop` + loguru warning.
   - Same for click buttons: only left/right/middle allowed.
3. **OCR grounding**: after grabbing each frame, run pytesseract OCR on the frame (tesseract at C:/Program Files/Tesseract-OCR/tesseract.exe; upscale x1.5 LANCZOS + threshold 140 first) and pass detected words (top 15, with coords) into the agent via a new optional kwarg: extend `VLMAgent.decide(observation, context: str | None = None)` in qa_framework/gameplay_agent/vlm_agent.py — context string appended to the prompt. Keep backward compat (default None).
4. Update tests in tests/test_vlm_agent.py: add a test that decide() with context includes it in the prompt (EchoVLMBackend records prompts it receives).

## Acceptance criteria (run yourself)
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py qa_framework/gameplay_agent/vlm_agent.py tests/test_vlm_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_vlm_agent.py -q
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/live_gameplay_agent.py --help
```

## Report
End with `## A2A REPORT`.
