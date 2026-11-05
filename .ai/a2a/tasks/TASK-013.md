# TASK-013: Skill curation — prune ineffective cached skills using reward data

## Goal
Close the learning loop: cached actions that consistently produce no screen change should be evicted.

## Changes
1. Extend `qa_framework/gameplay_agent/skill_cache.py`:
   - `record_outcome(sig, success: bool)` — tracks per-sig outcome counts in memory (not persisted): {sig: {"good": n, "bad": n}}.
   - In `get()`: if a sig has ≥3 recorded outcomes and ≥2/3 were failures (bad >= 2), delete the entry before returning (log "pruned ineffective skill") and return None so the VLM re-decides.
2. Wire into `scripts/live_gameplay_agent.py`: after computing reward each step, call `cache.record_outcome(sig, reward > 0.0)` for the sig that produced the action.
3. Tests in tests/test_skill_cache.py: record_outcome + eviction after 2 fails of 3; successful skills survive.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent scripts/live_gameplay_agent.py tests/test_skill_cache.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_skill_cache.py -q
```

## Report
End with `## A2A REPORT`.
