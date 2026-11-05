# TASK-015: Multi-game profiles

## Goal
Make the live loop game-agnostic via config, ready for SHINEBRINGERS and Unforgettable Love.

## Changes
1. New file `scripts/game_profiles.json`:
```json
{
  "agent-veil": {
    "window_title": "Agent Veil",
    "menu_keywords": ["tutorial", "setting", "exit", "play", "start", "lobby", "create", "join", "continue", "cancel", "back", "close", "yes", "no", "confirm", "name", "host", "room", "code"],
    "exe_path": "D:/SteamLibrary/steamapps/common/AgentVeilDemo/AgentVeil.exe"
  },
  "shinebringers": {
    "window_title": "SHINEBRINGERS",
    "menu_keywords": ["tutorial", "setting", "exit", "play", "start", "lobby", "create", "join", "continue", "cancel", "back", "close", "yes", "no", "confirm"],
    "exe_path": ""
  }
}
```
2. `scripts/live_gameplay_agent.py`: add `--profile <name>` arg (default agent-veil). Load window_title + menu_keywords + exe_path from the JSON. exe_path empty → skip auto-launch hint in the not-found error message.
3. SkillCache path becomes per-profile: `.ai/a2a/skills_<profile>.json` so learned skills don't cross-contaminate games.
4. No changes to qa_framework package needed.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/live_gameplay_agent.py --help
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -c "import json; d=json.load(open('scripts/game_profiles.json')); assert 'shinebringers' in d and d['shinebringers']['window_title']=='SHINEBRINGERS'"
```

## Report
End with `## A2A REPORT`.
