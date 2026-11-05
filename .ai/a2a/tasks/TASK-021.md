# TASK-021: Auto-dispatch ranked alternative skills

## Goal
Promote the TASK-020 observability hook into real action: when the agent is stuck (reward==0.0 twice in a row on the same OCR state) AND no fuzzy cache hit exists, consult `rank_by_ocr` and actually try the top-ranked alternative action instead of only logging it.

## Changes to `scripts/live_gameplay_agent.py`
1. Track `zero_streak` (consecutive zero-reward steps) and `last_ocr_part`.
2. When `decide()` returns and `reward==0.0` and `last_ocr_part` unchanged and `zero_streak >= 2`:
   - Call `self._cache.rank_by_ocr(last_ocr_part, top_k=3)`.
   - If the top alternative action differs from the one just executed, dispatch it (via the same executor path) and log "trying ranked alternative: <action> (ratio=X.XX)"; do NOT call VLM again this step.
   - Guard: only try one alternative per stuck episode; reset `zero_streak` after a non-zero reward or a state change.
3. Keep the existing stuck-escape (inject escape) as a fallback if no ranked alternative exists.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_skill_cache.py tests/test_vlm_agent.py tests/test_reward.py tests/test_gameplay_agent.py -q
```
Also add a unit test `tests/test_live_alternative.py` that constructs a GameplayAgent-like harness (mock backend, mock executor) and verifies: after 2 zero rewards on same OCR part with a known good alternative in cache, the alternative action is dispatched.

## Report
End with `## A2A REPORT`.
