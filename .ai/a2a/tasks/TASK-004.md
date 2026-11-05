# TASK-004: Live smoke script — VLMAgent driving a synthetic frame via LM Studio

## Goal
Create `scripts/live_vlm_smoke.py`: an end-to-end smoke test that runs `VLMAgent` + `OpenAICompatBackend` against the local LM Studio server and executes the decided action through `ActionExecutor` with mocked keyboard/mouse (no real input during smoke).

## Requirements
1. Script flow:
   - Generate a synthetic BGR frame with cv2 (e.g. 640x480 solid color + text "MENU" drawn) — do NOT capture a real game.
   - Build `OpenAICompatBackend(base_url="http://localhost:1234/v1", model="google/gemma-4-e2b", api_key="lm-studio")`.
   - Build `VLMAgent(backend, allowed_actions=["key_press","click","mouse_move","noop"])`.
   - Call `observe(frame)` then `decide(frame)`; print the raw backend response, parsed action, then `ActionExecutor(keyboard=Mock(), mouse=Mock())` dispatch (use `unittest.mock.Mock`).
   - Print PASS if decide() returned one of allowed actions; else FAIL with exit code 1.
   - Support `--iterations N` flag (default 3): loop decide() N times appending history.
2. Keep it importable-safe (`if __name__ == "__main__":`), loguru logging.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_vlm_smoke.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/live_vlm_smoke.py --iterations 2
```
The second command must print PASS and exit 0 (LM Studio runs at localhost:1234 — it is already up).

## Report
End with `## A2A REPORT` + paste the actual script output.
