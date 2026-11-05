# TASK-019: Live loop robustness hardening

## Goal
Fix weaknesses that would bite during long unattended runs.

## Changes to `scripts/live_gameplay_agent.py`:
1. **VLM timeout**: OpenAICompatBackend currently has no request timeout — add `timeout: float = 120.0` ctor arg, pass to `urllib.request.urlopen(req, timeout=...)`. In live script use 90s; on timeout the decide() fallback path already handles it (verify).
2. **Consecutive-error guard**: if VLMAgent falls back (parse fail or backend error) N=3 times in a row, pause 30s before next step (give model/window time to recover) and log "backing off after consecutive failures".
3. **Graceful Ctrl+C**: wrap main loop in try/except KeyboardInterrupt → print "interrupted by user", still write trace file, exit 0.
4. **Trace flush**: append each step's JSONL line immediately (open in append mode per step) so a crash doesn't lose history.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py qa_framework/gameplay_agent/backends.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/live_gameplay_agent.py --help
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_vlm_agent.py tests/test_skill_cache.py tests/test_reward.py tests/test_gameplay_agent.py -q
```

## Report
End with `## A2A REPORT`.
