# TASK-016: Session QA report from skill_trace.jsonl

## Goal
Turn run traces into an inspectable report using the existing QA reporting stack.

## Changes
1. New script `scripts/session_report.py`:
   - Args: `--trace <path>` (default .ai/a2a/skill_trace.jsonl), `--out <path>` (default .ai/a2a/report.html).
   - Reads JSONL entries {sig, action, params, cached, reward} and renders a self-contained HTML file (no external deps): summary stats table (total steps, unique states, cache hit rate %, mean reward, progression rate = fraction reward>0), per-step table (step #, action, params, cached?, reward), and a simple inline SVG bar chart of rewards per step.
2. Register nothing in the GUI; keep it CLI-only for now.

## Acceptance criteria
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check scripts/session_report.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe scripts/session_report.py && test -f .ai/a2a/report.html && echo REPORT_OK
```

## Report
End with `## A2A REPORT`.
