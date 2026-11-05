# TASK-005: Real-game loop script — Agent Veil Demo driven by VLMAgent

## Goal
Create `scripts/live_gameplay_agent.py`: capture the real Agent Veil Demo window, feed frames to VLMAgent (LM Studio gemma-4-e2b), dispatch decided actions via REAL keyboard/mouse services, with a safety kill-switch.

## Requirements
1. Reuse existing capture approach from `.ai/explore_av3.py` (EnumWindows find "AgentVeil" title + mss grab by window rect). Copy the needed helpers into the script — do NOT import from `.ai/`.
2. Loop (`--max-steps N`, default 10):
   - grab frame → `agent.decide(frame)` → print raw action → `ActionExecutor` with REAL KeyboardService/MouseService (no mocks) → `time.sleep(2)` between steps.
   - Kill-switch: check `GetAsyncKeyState(VK_ESCAPE)`-style via ctypes each iteration; if F12 pressed → exit cleanly printing "KILLED BY USER". Also hard cap by max-steps.
   - Allowed actions: key_press (params: key), mouse_move (x,y relative to window rect), click (button). Constrain mouse coords to within window bounds.
   - Before first decide, send one click at window center to ensure game focus.
3. Safety: if game window not found → print clear error and exit 1 without sending any input.
4. Do not launch the game yourself; assume it is already running.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/live_gameplay_agent.py --help
```
Both must succeed (the --help run must NOT require the game to be running).

## Report
End with `## A2A REPORT`.
