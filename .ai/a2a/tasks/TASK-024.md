# TASK-024: Per-game-type taxonomy + strategy separation

## Goal
Separate the agent's behavior by GAME TYPE so each genre gets an appropriate decision strategy, not a one-size-fits-all menu loop.

## Observed games (D:/SteamLibrary/steamapps/common)
- SHINEBRINGERS Demo → SwishAndFlickDemo.exe (SwishAndFlick) — ACTION/ARCADE (flick/projectile, real-time, no text menu)
- AgentVeilDemo → AgentVeil.exe — MENU/ADVENTURE (main menu: Create Lobby/Join/Tutorial/Settings/Exit; submenus need keyboard)
- Unforgettable Love → Unforgettable_Love.exe — VISUAL NOVEL (dialogue, click-to-advance, choices)

## Changes
### 1. `scripts/game_profiles.json` — extend each profile with `game_type` and `strategy`:
```json
{
  "shinebringers": {"exe":"...SwishAndFlickDemo.exe","window_title":"SwishAndFlick","game_type":"action","strategy":"realtime_flick",
                    "menu_keywords":[], "ocr_min_conf": 40},
  "agent-veil":   {"exe":"...AgentVeil.exe","window_title":"Agent Veil ","game_type":"menu","strategy":"menu_nav",
                    "menu_keywords":["create lobby","join","tutorial","settings","exit","cancel","back","confirm"], "ocr_min_conf": 60},
  "unforgettable-love": {"exe":"...Unforgettable_Love.exe","window_title":"Unforgettable Love","game_type":"visual_novel","strategy":"vn_advance",
                    "menu_keywords":["next","skip","save","load","settings","choice","yes","no"], "ocr_min_conf": 55}
}
```
### 2. `scripts/live_gameplay_agent.py`:
- Load profile; branch on `strategy`:
  - `menu_nav`: existing behavior (unchanged).
  - `realtime_flick` (action): skip menu-keyword matching; VLM/MOA decides continuous actions (mouse drag = flick); no stuck-escape keyboard (game has no menus).
  - `vn_advance` (visual novel): prefer `click` to advance dialogue; if OCR shows a `choice` keyword, click that word's coords; skip reward-based cache pruning (VN is linear).
- Log which strategy is active: "strategy=<name>".
### 3. `qa_framework/gameplay_agent/vlm_agent.py`: pass `strategy` + `menu_keywords` into the prompt so the VLM knows the genre context.
### 4. Tests: tests/test_game_profiles.py — load JSON, assert 3 profiles with correct game_type; assert strategy dispatch key exists.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py qa_framework/gameplay_agent/vlm_agent.py scripts/game_profiles.json tests/test_game_profiles.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_game_profiles.py -q
```
(No live run required — strategy branching is unit-tested via a mock that asserts the right branch is taken for each game_type. If a game window is up, a short --profile <game> --max-steps 2 smoke is encouraged.)

## Report
End with `## A2A REPORT`.
