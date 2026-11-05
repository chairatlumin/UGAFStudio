# TASK-002: Fix remaining lint errors in qa_framework/gameplay_agent

## Goal
Make the acceptance commands of TASK-001 pass. Known remaining errors from `ruff check`:
- E501 line-too-long in `qa_framework/gameplay_agent/actions.py` lines ~91, 99, 107 (long conditional service instantiation — refactor to a small helper `_get_default_service()`).
- F821 undefined name `Action` in `qa_framework/gameplay_agent/base.py` line 19 (missing import).

## Steps
1. Run `cd C:/Users/Admin/UGAFStudio && PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent tests/test_gameplay_agent.py` and fix every reported error.
2. Then run pytest on tests/test_gameplay_agent.py until green.

## Acceptance criteria
Both commands exit 0:
```
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent tests/test_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_gameplay_agent.py -q
```

## Report
End with `## A2A REPORT` listing files changed + final test summary.
