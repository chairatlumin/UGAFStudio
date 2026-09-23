"""Cost tracking and metrics for UGAFStudio QA runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


class CostEntry(TypedDict):
    checkpoint: str
    tokens: int
    cost_usd: float


@dataclass
class CostTracker:
    """Track token usage and cost per checkpoint."""

    entries: list[CostEntry] = field(default_factory=list)
    _decisions: dict[str, dict[str, float]] = field(default_factory=dict)

    def log(self, checkpoint_name: str, tokens: int, cost_usd: float) -> None:
        self.entries.append({
            "checkpoint": checkpoint_name,
            "tokens": tokens,
            "cost_usd": cost_usd,
        })

    def record_checkpoint_cost(
        self,
        checkpoint_name: str,
        tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Record cost attributed to a specific checkpoint/decision.

        Per-decision attribution enables cost-per-checkpoint analysis
        for 2026 agent observability patterns.
        """
        if checkpoint_name not in self._decisions:
            self._decisions[checkpoint_name] = {
                "tokens": 0,
                "cost_usd": 0.0,
                "count": 0,
            }
        self._decisions[checkpoint_name]["tokens"] += tokens
        self._decisions[checkpoint_name]["cost_usd"] += cost_usd
        self._decisions[checkpoint_name]["count"] += 1
        # Also log to entries for backward compat
        self.log(checkpoint_name, tokens, cost_usd)

    @property
    def total_tokens(self) -> int:
        return sum(e["tokens"] for e in self.entries)

    @property
    def total_cost(self) -> float:
        return float(sum(e["cost_usd"] for e in self.entries))

    def cost_per_correct(self) -> float:
        """Cost per correct checkpoint. Returns 0.0 if no entries."""
        if not self.entries:
            return 0.0
        correct = sum(1 for e in self.entries if e["tokens"] > 0)
        if correct == 0:
            return 0.0
        return self.total_cost / correct

    def summary(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost, 6),
            "checkpoints_logged": len(self.entries),
            "cost_per_correct_usd": round(self.cost_per_correct(), 6),
            "decisions": self._decisions,
            "entries": self.entries,
        }


@dataclass
class RecoveryTracker:
    """Track recovery incidents and compute recovery rate."""

    incidents: int = 0
    recoveries: int = 0
    actions: list[dict] = field(default_factory=list)

    def record_incident(self, action_taken: str, success: bool) -> None:
        """Record a recovery incident.

        Args:
            action_taken: The recovery action that was attempted (e.g., "retry", "relaunch").
            success: Whether the recovery succeeded.
        """
        self.incidents += 1
        if success:
            self.recoveries += 1
        self.actions.append({"action": action_taken, "success": success})

    @property
    def recovery_rate(self) -> float:
        """Compute recovery rate. Returns 1.0 if no incidents (perfect)."""
        if self.incidents == 0:
            return 1.0
        return self.recoveries / self.incidents

    def summary(self) -> dict:
        return {
            "incidents": self.incidents,
            "recoveries": self.recoveries,
            "recovery_rate": round(self.recovery_rate, 4),
            "actions": self.actions,
        }
