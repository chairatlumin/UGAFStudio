# TASK: CascadeDispatchRouter + PerceptionDriftDetector + StatisticalTestRunner

## Goal
Create 3 new modules in `qa_framework/` for agent model escalation, visual drift detection, and statistical game QA testing.

## Context

**Existing codebase (DO NOT break):**
- `C:/Users/Admin/UGAFStudio/qa_framework/` contains ~28 Python files (a2a_adapter, vision_game_runner, cost_optimization, speculative_dispatch, etc.)
- 83 existing tests all passing
- Python 3.14 interpreter at `C:/Python314/python.exe`
- All Python commands must use `PYTHONPATH=C:/Users/Admin/UGAFStudio`

**Reference plan:**
- `C:/Users/Admin/.hermes/plans/plan-2026-09-23-2345.md` (full TDD steps)

## Requirements

1. Create `qa_framework/cascade_dispatch.py` — CascadeDispatchRouter + EscalationPolicy
2. Create `qa_framework/perception_drift.py` — PerceptionDriftDetector
3. Create `qa_framework/statistical_runner.py` — StatisticalTestRunner
4. Create test files for each (3 tests each = 9+ new tests)
5. All 83 existing tests must continue passing
6. stdlib only — no new pip imports

## Architecture Rules

- Pure Python stdlib only
- Dataclasses for data containers
- Type hints throughout
- Concise, readable code — no over-engineering
- Python 3.14+ syntax allowed

## Exact Validation Commands

```bash
cd C:/Users/UGAFStudio

# 1. All tests must pass (83 existing + ~16 new = ~99)
PYTHONPATH=C:/Users/Admin/UGAFStudio python -m pytest qa_framework/tests/test_cascade_dispatch.py qa_framework/tests/test_perception_drift.py qa_framework/tests/test_statistical_runner.py qa_framework/tests/test_a2a_adapter.py qa_framework/tests/test_vision_game_runner.py qa_framework/tests/test_cost_optimization.py -v

# 2. Type checking must pass
PYTHONPATH=C:/Users/Admin/UGAFStudio python -m mypy qa_framework/cascade_dispatch.py qa_framework/perception_drift.py qa_framework/statistical_runner.py

# 3. Linting must pass
PYTHONPATH=C:/Users/Admin/UGAFStudio python -m ruff check qa_framework/cascade_dispatch.py qa_framework/perception_drift.py qa_framework/statistical_runner.py qa_framework/tests/test_cascade_dispatch.py qa_framework/tests/test_perception_drift.py qa_framework/tests/test_statistical_runner.py

# 4. Git diff stat
git diff --stat
```

## Implementation Details

### cascade_dispatch.py

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class EscalationPolicy:
    """Rules for when to escalate to a stronger model."""
    require_json: bool = False
    min_output_length: int = 10
    forbidden_terms: list[str] = field(default_factory=list)
    max_consecutive_failures: int = 2

    def should_escalate(self, output: str, model: str) -> bool:
        if len(output.strip()) < self.min_output_length:
            return True
        if self.require_json:
            try:
                json.loads(output)
            except (json.JSONDecodeError, TypeError):
                return True
        for term in self.forbidden_terms:
            if term.lower() in output.lower():
                return True
        return False


@dataclass
class CascadeDispatchRouter:
    """Routes A2A briefs through a cascade of models with quality-based escalation."""
    models: list[str]
    policy: EscalationPolicy = field(default_factory=EscalationPolicy)
    _current_index: int = 0
    _failure_counts: dict[str, int] = field(default_factory=dict)
    _total_dispatches: int = 0
    _escalations: int = 0
    _model_usage: dict[str, int] = field(default_factory=lambda: {})

    @property
    def current_model(self) -> str:
        if self._current_index < len(self.models):
            return self.models[self._current_index]
        return self.models[-1]

    def record_result(self, model: str, output: str) -> bool:
        self._total_dispatches += 1
        self._model_usage[model] = self._model_usage.get(model, 0) + 1
        if self.policy.should_escalate(output, model):
            self._failure_counts[model] = self._failure_counts.get(model, 0) + 1
            if self._failure_counts[model] >= self.policy.max_consecutive_failures:
                self._escalate()
            return False
        else:
            self._failure_counts[model] = 0
            self._current_index = 0
            return True

    def _escalate(self) -> None:
        if self._current_index < len(self.models) - 1:
            self._current_index += 1
            self._escalations += 1

    def record_connection_error(self, model: str) -> None:
        self._failure_counts[model] = self.policy.max_consecutive_failures + 1
        self._escalate()

    def cost_report(self) -> dict:
        return {
            "total_dispatches": self._total_dispatches,
            "escalation_count": self._escalations,
            "escalation_rate": round(self._escalations / max(1, self._total_dispatches), 4),
            "model_usage": dict(self._model_usage),
            "current_model": self.current_model,
        }
```

### perception_drift.py

```python
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field


def _perceptual_hash(data: str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()[:32]


def _similarity(hash_a: str, hash_b: str) -> float:
    if len(hash_a) != len(hash_b):
        return 0.0
    matches = sum(1 for a, b in zip(hash_a, hash_b) if a == b)
    return matches / len(hash_a)


@dataclass
class PerceptionDriftDetector:
    threshold: float = 0.85
    _references: dict[str, str] = field(default_factory=dict)
    _drift_counts: dict[str, int] = field(default_factory=dict)

    def set_reference(self, scene: str, frame_data: str) -> None:
        self._references[scene] = _perceptual_hash(frame_data)

    def check_drift(self, scene: str, frame_data: str) -> dict:
        if scene not in self._references:
            return {"drifted": None, "similarity": None, "scene": scene}
        ref_hash = self._references[scene]
        cur_hash = _perceptual_hash(frame_data)
        sim = _similarity(ref_hash, cur_hash)
        drifted = sim < self.threshold
        if drifted:
            self._drift_counts[scene] = self._drift_counts.get(scene, 0) + 1
        return {"drifted": drifted, "similarity": round(sim, 4), "scene": scene}

    def report(self) -> dict:
        scenes = []
        for scene, ref_hash in self._references.items():
            scenes.append({
                "scene": scene,
                "drift_count": self._drift_counts.get(scene, 0),
            })
        return {
            "scenes": scenes,
            "total_scenes": len(scenes),
            "threshold": self.threshold,
        }
```

### statistical_runner.py

```python
from __future__ import annotations
import math
from dataclasses import dataclass, field


@dataclass
class StatisticalTestRunner:
    runs: int = 10
    pass_threshold: float = 0.8
    confidence: float = 0.95

    def run(self, game_runner) -> dict:
        successes = 0
        total = 0
        for _ in range(self.runs):
            results = game_runner.run_all()
            for r in results:
                total += 1
                if r.get("success"):
                    successes += 1
        pass_rate = successes / max(1, total)
        ci_low, ci_high = self._confidence_interval(pass_rate, total)
        return {
            "runs": self.runs,
            "total_runs": total,
            "passes": successes,
            "pass_rate": round(pass_rate, 4),
            "confidence_interval": (round(ci_low, 4), round(ci_high, 4)),
            "passed": pass_rate >= self.pass_threshold,
        }

    def _confidence_interval(self, p: float, n: int) -> tuple[float, float]:
        if n == 0:
            return (0.0, 1.0)
        z = 1.96 if self.confidence >= 0.95 else 1.645
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
        return (max(0.0, center - spread), min(1.0, center + spread))
```

### Tests

**test_cascade_dispatch.py** — 7 tests covering escalation policy, router escalation, cost tracking, fallback

**test_perception_drift.py** — 5 tests covering drift detection, similarity, unknown scenes, multi-scene tracking

**test_statistical_runner.py** — 4 tests covering pass rate, confidence intervals, threshold enforcement

## Report Format

Reply with:
- Status: SUCCESS or FAILURE
- Components: list (CascadeDispatchRouter + PerceptionDriftDetector + StatisticalTestRunner)
- Tests: count (new tests across 3 modules)
- Validation: pytest/mypy/ruff summary
- Files changed: list
- Issues or deviations

## Critical
- If validation commands fail, FIX the code before reporting success
- Do NOT disable or modify existing tests
- Do NOT add new pip dependencies
- Use Python 3.14 interpreter at C:/Python314/python.exe
- Project dir: C:/Users/UGAFStudio
- Run with PYTHONPATH=C:/Users/UGAFStudio
