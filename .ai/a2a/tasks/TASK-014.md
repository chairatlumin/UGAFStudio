# TASK-014: Submenu progression — escape guidance + text-input action

## Goal
The live agent gets stuck on Create Lobby/Join submenus (v10: all reward=0). Extend its vocabulary to progress through them.

## Changes
1. `scripts/live_gameplay_agent.py` MENU_KEYWORDS: add {cancel, back, close, yes, no, confirm, name, host, join, room, code}.
2. Allowed keys already include escape/tab/e/q — good. Add explicit stuck-state recovery in the loop: after 3 consecutive reward=0.0 steps, inject ONE key_press escape (log "stuck: injecting escape") and reset the consecutive counter. Keep existing loop-guard injection too, but escape takes priority.
3. Add `type_text` to allowed_actions passed to VLMAgent (ActionExecutor already supports it) so lobby-name prompts can be filled; params whitelist: any printable string up to 32 chars, stripped.
4. Tests: none required for script logic (manual verification), but ensure ruff passes.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/live_gameplay_agent.py --help
```

## Report
End with `## A2A REPORT`.
