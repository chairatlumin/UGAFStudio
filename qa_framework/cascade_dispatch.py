from __future__ import annotations

import json
from dataclasses import dataclass, field


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
