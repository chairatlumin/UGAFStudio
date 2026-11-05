# TASK-010: Menu-targeting — click exact items by OCR coords

## Goal
Stop blind center-clicks; when the VLM decides to click and the OCR context contains a known menu word, click that word's position.

## Changes
1. In `scripts/live_gameplay_agent.py` add `resolve_click_target(params, ocr_words, window_rect) -> (x, y)`:
   - If params already contain x,y → clamp into window bounds and use them.
   - Else find first OCR word whose text matches a menu keyword set {tutorial, setting(s), exit, play, start, lobby, create, join, continue} (case-insensitive substring match) → target = word center + window offset.
   - Else fallback: window center.
   - Return absolute screen coords for mouse_move+click dispatch sequence.
2. When action==click and a resolved target exists, dispatch as two actions: `mouse_move{x,y}` then `click{button}` (both via ActionExecutor) so the cursor actually reaches the menu item. Log the chosen target word + coords.
3. Keep everything else unchanged.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/live_gameplay_agent.py --help
```

## Report
End with `## A2A REPORT`.
