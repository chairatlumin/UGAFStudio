from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class GameRunnerProtocol(Protocol):
    def run_all(self) -> list[dict]: ...


@dataclass
class StatisticalTestRunner:
    """Run game QA scenarios N times and assert pass rate with confidence."""
    runs: int = 10
    pass_threshold: float = 0.8
    confidence: float = 0.95

    def run(self, game_runner: GameRunnerProtocol) -> dict:
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
        """Wilson score interval for binomial proportion."""
        if n == 0:
            return (0.0, 1.0)
        z = 1.96 if self.confidence >= 0.95 else 1.645
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
        return (max(0.0, center - spread), min(1.0, center + spread))
