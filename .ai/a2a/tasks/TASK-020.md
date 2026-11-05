# TASK-020: Reward-weighted skill selection across similar states

## Goal
When the exact state is unknown but OCR words match a known successful state, reuse its best action (currently fuzzy matching only fires when the sig is missing entirely).

## Changes
1. `qa_framework/gameplay_agent/skill_cache.py`:
   - Add `rank_by_ocr(ocr_words_sig_part: str, top_k: int = 3) -> list[dict]`: return entries whose sig's OCR part equals `ocr_words_sig_part` (exact string compare of the pre-hash portion), sorted by success ratio desc, filtered to ratio >= 0.5 and >=1 sample. Each item: {sig, action, params, ratio}.
   - Reuse `extract_ocr_prefix` logic internally (factor into helper `_ocr_part(sig)` if not already usable).
2. `scripts/live_gameplay_agent.py`: after a normal decide() with reward==0.0 for the same OCR part twice in a row, consult `rank_by_ocr` and log the alternatives ("alternatives for state X: ...") to aid debugging. Do NOT auto-dispatch them yet (observability first).
3. Tests in tests/test_skill_cache.py: rank_by_ocr ordering, ratio filtering, empty result.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent scripts/live_gameplay_agent.py tests/test_skill_cache.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_skill_cache.py -q
```

## Report
End with `## A2A REPORT`.
