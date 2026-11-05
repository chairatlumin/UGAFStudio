# TASK-001: GameplayAgent base interface + input/capture adapters

## Goal
Create a Python package `qa_framework/gameplay_agent/` in this repo with:
1. `base.py` — abstract class `GameplayAgent` with methods:
   - `observe(self, frame: np.ndarray) -> Any` (receive a game frame)
   - `decide(self, observation: Any) -> "Action"` where Action is a dataclass(action: str, params: dict)
   - `learn(self, reward: float, done: bool) -> None` (no-op by default; for future RL models)
2. `random_agent.py` — `RandomAgent(GameplayAgent)` that picks from a configurable action list (e.g. w/a/s/d/space/mouse_move/click).
3. `actions.py` — `Action` dataclass and an `ActionExecutor` that maps Actions to the existing automation services in `qa_framework/services/` (inspect what exists there first — reuse keyboard/mouse services if present).
4. Tests in `tests/test_gameplay_agent.py` covering RandomAgent determinism with a seeded rng, Action mapping, and executor dispatch (mock the underlying service).

## Context
- Repo root: C:/Users/Admin/UGAFStudio
- Existing framework: qa_framework package (Services contain business logic; Controllers orchestrate; Widgets never contain business logic — follow AGENTS.md).
- Capture already works elsewhere via PrintWindow; you only need to accept a numpy BGR frame.

## Constraints
- Python 3.14, style per existing code (loguru for logging, ruff clean, type hints required).
- No new heavy dependencies.

## Acceptance criteria
All of these pass (run them yourself):
```
cd C:/Users/Admin/UGAFStudio && PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent tests/test_gameplay_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_gameplay_agent.py -q
```

## Report
End your run with a section `## A2A REPORT` listing files created and test output summary.
