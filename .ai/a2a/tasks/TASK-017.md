# TASK-017: Reward-weighted skill ranking

## Goal
When multiple cached skills exist for similar states, prefer ones with proven success.

## Changes
1. Extend `qa_framework/gameplay_agent/skill_cache.py`:
   - Persist per-sig outcome stats alongside actions in the JSON: {sig: {"action":..., "params":..., "good": n, "bad": n}} — update `put()` to preserve existing good/bad counts when overwriting a sig; `record_outcome(sig, success)` updates counts AND persists them via save().
   - New method `best_sig_prefix(prefix: str) -> dict | None`: among entries whose sig starts with the prefix, return the action entry with highest success ratio good/(good+bad) (min 1 sample). Used for fuzzy state matching.
   - Keep existing pruning logic unchanged.
2. Wire into live script: on cache MISS, before calling the VLM, try `best_sig_prefix(visual_hash_part_of_sig)` — if found, use it as a "fuzzy cache hit" (log it) instead of a VLM call.
3. Tests in tests/test_skill_cache.py: put preserves counts on overwrite; record_outcome persists; best_sig_prefix picks highest-ratio entry.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent scripts/live_gameplay_agent.py tests/test_skill_cache.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_skill_cache.py -q
```

## Report
End with `## A2A REPORT`.
