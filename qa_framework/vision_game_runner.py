from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional


@dataclass
class GameScenario:
    """A single game test scenario (test case)."""
    name: str
    description: str
    expected_states: list[str] = field(default_factory=list)
    max_steps: int = 100
    timeout_seconds: float = 60.0
    tags: list[str] = field(default_factory=list)


@dataclass
class PerceptionState:
    """What the agent currently perceives about the game state."""
    detected_text: list[str] = field(default_factory=list)
    colors_dominant: list[tuple[int, int, int]] = field(default_factory=list)
    scene_classification: str = "unknown"
    confidence: float = 0.5
    raw_frame_hash: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ActionResult:
    """Result of a single action taken by the agent."""
    action: str
    success: bool
    state_before: str
    state_after: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""


class VisionGameRunner:
    """Vision-based game test runner using perception-action loop."""

    def __init__(
        self,
        perception_fn: Optional[Callable[[], PerceptionState]] = None,
        action_fn: Optional[Callable[[PerceptionState, GameScenario], str]] = None,
        executor_fn: Optional[Callable[[str], bool]] = None,
        max_steps_default: int = 100,
        step_delay: float = 0.5,
    ):
        self.scenarios: list[GameScenario] = []
        self.perception_fn = perception_fn or self._default_perception
        self.action_fn = action_fn or self._default_action
        self.executor_fn = executor_fn or self._default_executor
        self.max_steps_default = max_steps_default
        self.step_delay = step_delay

    def add_scenario(self, scenario: GameScenario) -> None:
        self.scenarios.append(scenario)

    def run_all(self) -> list[dict]:
        return [self._run_scenario(s) for s in self.scenarios]

    def _run_scenario(self, scenario: GameScenario) -> dict:
        start = datetime.now(timezone.utc).isoformat()
        actions: list[ActionResult] = []
        max_steps = min(scenario.max_steps, self.max_steps_default)
        current_state = "initial"
        success = False
        failure_reason = ""

        for step in range(max_steps):
            perception = self.perception_fn()
            action = self.action_fn(perception, scenario)
            executed = self.executor_fn(action)

            result = ActionResult(
                action=action,
                success=executed,
                state_before=current_state,
                state_after=perception.scene_classification,
            )
            actions.append(result)
            current_state = perception.scene_classification

            if current_state in scenario.expected_states:
                success = True
                break

            if not executed:
                failure_reason = f"Action '{action}' failed at step {step}"
                break

            time.sleep(self.step_delay)

        if not success and not failure_reason:
            failure_reason = f"Max steps ({max_steps}) reached without reaching expected state"

        return {
            "scenario": scenario.name,
            "success": success,
            "steps_taken": len(actions),
            "actions": [
                {
                    "action": a.action,
                    "success": a.success,
                    "state_before": a.state_before,
                    "state_after": a.state_after,
                    "notes": a.notes,
                }
                for a in actions
            ],
            "failure_reason": failure_reason,
            "start_time": start,
            "end_time": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _default_perception() -> PerceptionState:
        return PerceptionState(detected_text=[], colors_dominant=[], scene_classification="stub")

    @staticmethod
    def _default_action(perception: PerceptionState, scenario: GameScenario) -> str:
        return "wait"

    @staticmethod
    def _default_executor(action: str) -> bool:
        return True
