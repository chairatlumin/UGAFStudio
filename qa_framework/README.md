# UGAF Declarative QA Runner

Run a JSON suite from the project root:

```powershell
python -m qa_framework.run --suite qa_framework/examples/build_smoke.json
```

The runner executes supported checks, writes an HTML report to `reports/`, and
returns exit code `0` when every test passes, `1` when a test fails, or `2`
when the suite cannot be loaded.

Supported checks:

- `directory_exists`: verifies a directory relative to the suite file.
- `file_exists`: verifies a file relative to the suite file.
- `executable_count`: checks the number of `.exe` files in a directory.
- `engine_version_supported`: validates Unreal Engine `5.7` or `5.8`.

## Declarative Steam gameplay QA

Run a single-game testcase:

```powershell
C:\Users\Admin\QA-Bot\.venv\Scripts\python.exe -m qa_framework.gameplay_cli `
  --app-id 4077460 `
  --suite qa_framework/examples/game_4077460_shinebringers_live.json `
  --steam-root D:\SteamLibrary `
  --output-dir reports/live
```

Run a combined testcase for the configured games:

```powershell
C:\Users\Admin\QA-Bot\.venv\Scripts\python.exe -m qa_framework.gameplay_cli `
  --suite qa_framework/examples/gameplay_combined_live.json `
  --output-dir reports/live
```

A gameplay suite can configure `executable_name`, `capture_delay`,
`screenshot_dir`, and visual assertions (`color_detected`, `template_match`,
`frame_not_black`, or `ocr_contains`). Relative template and screenshot paths
are resolved from the testcase file. The runner captures evidence, writes an HTML report, and
cleans up the complete game process tree after every run.

Run the same suite against a packaged executable from any engine or launcher:

```powershell
python -m qa_framework.gameplay_cli `
  --suite qa_framework/examples/workspace_smoke.json `
  --executable C:\Games\MyGame\MyGame.exe
```

Enable bounded autonomous gameplay with a deterministic action bot:

```json
{
  "bot": {
    "enabled": true,
    "max_steps": 30,
    "step_interval": 0.25,
    "actions": [
      {"action": "press", "key": "enter"},
      {"action": "move", "direction": "forward"}
    ]
  }
}
```

The runner records bot actions, rewards, failures, screenshots, and cleanup in
the same HTML report. A VLM/MOA agent can be injected through the Python API in
place of the default deterministic action bot.

## HighSchool Blood regression data

The read-only scene/status/feedback snapshot and current coverage limits are
documented in `testcases/highschool_blood_README.md`. Run the available
black-frame smoke check with:

```powershell
python -m qa_framework.gameplay_cli `
  --app-id 4511150 `
  --suite qa_framework/examples/game_4511150_highschoolblood_auto.json `
  --steam-root D:\SteamLibrary `
  --output-dir reports/highschool_blood
```
## Gameplay interaction

Gameplay suites may include an `actions` array after launch. Supported actions are `press`, `interact`, `hold`, `release`, `move` (`forward`, `back`, `left`, `right`), `look`, `click`, `wait`, and `wait_for`.

Example:

```json
{
  "actions": [
    {"action": "press", "key": "enter"},
    {"action": "interact", "key": "e"},
    {"action": "move", "direction": "forward", "seconds": 3},
    {"action": "look", "dx": 180, "dy": 0}
  ]
}
```

Run a game-specific interaction suite with:

```powershell
C:\Python314\python.exe -m qa_framework.gameplay_cli `
  --suite qa_framework/examples/agentveil_interaction.json `
  --app-id 4307180 `
  --steam-root D:\SteamLibrary
```

All held keys are released during cleanup, including when an action or assertion fails. Use `wait_for` with a visual assertion when menu/loading timing is variable.
