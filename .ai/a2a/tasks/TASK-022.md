# TASK-022: Auto-generate session report after live run

## Goal
Always produce a QA report at the end of a live run so results are inspectable without a separate command.

## Changes
1. `scripts/live_gameplay_agent.py`: after the main loop (normal end or Ctrl+C), call `scripts/session_report.py` logic (import its `build_report(trace_path, out_html)` function) to regenerate `.ai/a2a/report.html` from the just-written `skill_trace.jsonl`. Log "session report written: <path>".
2. Add `scripts/session_report.py::build_report(trace_path: str|Path, out_html: str|Path) -> dict` returning the stats dict (steps, cache_hits, rewards sum, mean latency). Keep the existing `__main__` CLI.
3. Unit test tests/test_session_report.py: feed a tiny fake trace (3 lines) → assert build_report returns expected keys and writes HTML containing "<title>".

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/live_gameplay_agent.py scripts/session_report.py tests/test_session_report.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_session_report.py -q
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/live_gameplay_agent.py --max-steps 2  # must print "session report written"
```

## Report
End with `## A2A REPORT`.
