# A2A Run 2026-08-27 — Hermes(Planner) ↔ OpenCode(Engineer) + MOA Survey

## TASK-024: Per-game-type taxonomy + strategy separation — DONE (2026-08-27)
3 games classified by genre:
- agent-veil → menu/adventure (menu_nav: Create Lobby/Join/Tutorial/Settings/Exit)
- shinebringers (SwishAndFlick) → action/arcade (realtime_flick)
- unforgettable-love → visual novel (vn_advance: click-to-advance + choices)
game_profiles.json extended with game_type + strategy + per-genre menu_keywords + ocr_min_conf.
live script branches on strategy (menu_nav unchanged; realtime_flick skips menu-match; vn_advance prefers click + choice-targeting, no cache pruning).
VLM prompt gets genre context. Unit test tests/test_game_profiles.py.
Gates: ruff ✅ mypy 9 ✅ pytest 7 ✅
Live v19 (agent-veil): EXIT=0, strategy=menu_nav loaded, menu-targeting 'Setting:' working.

## Status: 24/24 tasks ✅ | ruff ✅ mypy ✅ pytest ✅

## Per-genre strategy summary
| Game | Type | Strategy | Notes |
|---|---|---|---|
| Agent Veil | menu | menu_nav | OCR menu-target + escape fallback |
| SHINEBRINGERS | action | realtime_flick | continuous mouse drag, no menu |
| Unforgettable Love | vn | vn_advance | click-advance + choice-target |
