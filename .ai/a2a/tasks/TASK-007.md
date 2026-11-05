# TASK-007: Skill cache + faster VLM responses

## Goal
Cut decision latency by (a) caching successful action sequences per game state and (b) constraining VLM output.

## Changes
1. **SkillCache** — new file `qa_framework/gameplay_agent/skill_cache.py`:
   - Class `SkillCache(path: str | Path = "skills.json")`.
   - Key = normalized state signature: `signature(ocr_words) -> str` = sorted word texts lowercased joined (ignore coords).
   - Methods: `get(sig) -> Action | None`, `put(sig, action)`; persisted as JSON `{sig: {"action":..., "params":...}}`. Max 200 entries, FIFO eviction.
   - Thread-safe not required.
2. **VLMAgent integration**: add optional `cache: SkillCache | None = None` kwarg to `__init__`. In `decide()`: if cache has signature(observation's context words) → return cached Action immediately WITHOUT calling backend (log "skill cache hit"). On backend success → `cache.put(sig, action)`. Signature derived from a new optional param `state_sig: str | None` passed to decide(); if None skip caching.
   - Extend decide signature: `decide(self, observation, context=None, state_sig=None) -> Action` (backward compatible).
3. **Latency**: in `scripts/live_gameplay_agent.py` pass `"max_tokens": 60` request option through OpenAICompatBackend — add `max_tokens: int = 256` ctor arg included in payload. Also set live script to use it with 60. Append the raw VLM response text of each step into `.ai/a2a/skill_trace.jsonl` (one JSON line per step: ts-less fields {sig, action, params, cached}) for later analysis.
4. **Live script**: build SkillCache at startup, compute sig from OCR words each step, use agent cache path.
5. Tests in tests/test_skill_cache.py: put/get roundtrip, persistence to disk, FIFO eviction, VLMAgent cache hit skips backend (EchoVLMBackend with call counter).

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=... C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent scripts/live_gameplay_agent.py tests/test_skill_cache.py tests/test_vlm_agent.py
PYTHONPATH=... C:/Python314/python.exe -m pytest tests/ -q
```
(PYTHONPATH=C:/Users/Admin/UGAFStudio)

## Report
End with `## A2A REPORT`.
