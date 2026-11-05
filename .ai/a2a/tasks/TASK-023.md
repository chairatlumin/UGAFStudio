# TASK-023: MOA — Mixture of Agents voting for game actions

## Goal
Improve decision robustness by combining multiple VLM "agents" and taking the majority/reward-weighted vote, instead of a single brain call.

## Design
- New file `qa_framework/gameplay_agent/moa.py`:
  - `class MOAAgent`: ctor takes a list of `VLMAgent` instances (each with its own backend/model) + optional `weights: list[float]`.
  - `decide(state_sig, ocr_words, frame, history) -> Action`:
    1. Query ALL sub-agents in parallel (ThreadPoolExecutor, timeout per call = inherited backend timeout).
    2. Normalize each returned action via existing `normalize_action`/`ActionExecutor` whitelist.
    3. Vote: count normalized action strings; winner = most common. Tie-break: highest model weight; if all fail/timeout → fall back to first agent's action (or cache).
    4. Return winning Action.
  - `backend_errors` counter for observability.
- `scripts/live_gameplay_agent.py`: add `--moa` flag. When set, build MOAAgent from: qwen/qwen2.5-vl-7b (weight 1.0), google/gemma-4-e2b (0.6), qwen/qwen3.8-27b (0.4) — primary is fast, others cross-check. Log "MOA vote: <winner> (counts={...})".
- Unit test tests/test_moa.py: mock 3 backends returning conflicting actions → assert majority wins; all-fail → fallback path.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent/moa.py scripts/live_gameplay_agent.py tests/test_moa.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_moa.py -q
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m mypy qa_framework/gameplay_agent/
```
(Do NOT require a live game run for this task; MOA logic is unit-tested. But if a game window + models are loaded, a short `--moa --max-steps 2` smoke is encouraged.)

## Report
End with `## A2A REPORT`.
