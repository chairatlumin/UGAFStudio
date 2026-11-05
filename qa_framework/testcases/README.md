# Reusable Game QA Testcases

This directory contains a reusable testcase catalog, data sets, and a runnable
starter suite for packaged Windows games. The gameplay runner launches games
through their executable, so testcase design is independent of Unreal, Unity,
Godot, or a custom engine. The current input backend uses Windows foreground
keyboard and mouse input.

## Run the starter suite

Copy `starter_suite.json` beside your game-specific QA files, set the expected
text and visual checks for the game's first screen, then run:

```powershell
python -m qa_framework.gameplay_cli `
  --suite qa_framework/testcases/starter_suite.json `
  --executable 'C:\Games\MyGame\MyGame.exe' `
  --name 'My Game' `
  --output-dir reports/my-game
```

The starter is intentionally configured to fail its placeholder assertion
until a tester supplies a real expected label. This prevents an empty or
unconfigured suite from reporting a false pass. Configure `monitor_index`,
`capture_delay`, and screenshot resolution to match the test machine. Assertion
regions are pixel coordinates in the captured frame.

## Adapting testcase catalog entries

`catalog.json` defines engine-neutral scenarios and genre-oriented extensions.
For each game, map the logical action names to that game's controls, replace
expected UI labels with stable game text, and set meaningful visual regions.
Use a distinct suite for each game and keep test data in `data/` so runs can be
repeated and compared.

The catalog is a test design and data source; it is not loaded directly by the
runner. A visual assertion can validate observable screen state, while game
rules such as server authority, economy correctness, save integrity, and
anti-cheat behavior require game-specific instrumentation or backend checks.
Online tests should use a dedicated test environment and accounts.

## Data sets

- `data/boundary_values.json`: Unicode, length boundaries, and unusual names
  for name, chat, search, and profile fields.
- `data/economy_cases.json`: deterministic balance, purchase, reward, and
  inventory scenarios for games with currencies or items.
- `data/session_cases.json`: reconnect, interruption, persistence, and
  multiplayer session scenarios.

Each data case includes a stable ID, setup, input, and expected outcome. Treat
the values as synthetic test data; adapt limits and expected results to the
game's rules.
