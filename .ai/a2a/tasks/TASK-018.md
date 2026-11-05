# TASK-018: Smoke test new engineer model + latency benchmark harness

## Goal
Two things:
1. Confirm the A2A pipeline works with the new engineer model (hy3-free) by completing this task successfully.
2. Add a benchmark mode to measure decision latency per VLM backend.

## Changes
Create `scripts/bench_brain.py`:
- Args: `--models` (comma-separated LM Studio model ids, default "google/gemma-4-e2b"), `--steps` (default 5).
- For each model: capture one frame from the Agent Veil window (reuse PrintWindow helper logic from live_gameplay_agent.py), then run N decide() calls via VLMAgent+OpenAICompatBackend(model=model), timing each. Print per-model summary: mean/median/max seconds, parse-failure count.
- Do NOT dispatch any real input; Mock executor.
- Handle model-not-loaded errors gracefully (print SKIP for that model).

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/bench_brain.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/bench_brain.py --steps 2
```
(The game window should be running; if not found, script must exit 1 with clear message.)

## Report
End with `## A2A REPORT` including actual bench output.
