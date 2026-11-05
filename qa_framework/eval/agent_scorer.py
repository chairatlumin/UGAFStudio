"""Agent scoring metrics for evaluation pipeline."""

from __future__ import annotations


class AgentScorer:
    """Scores agent performance across coverage, bug detection, consistency, efficiency."""

    def __init__(self, memory_router_path: str | None = None) -> None:
        self.memory_router_path = memory_router_path

    def compute_coverage(self, states_visited: set[str], total_known_states: set[str]) -> float:
        """Fraction of known states visited by the agent."""
        if not total_known_states:
            return 1.0
        if not states_visited:
            return 0.0
        return len(states_visited & total_known_states) / len(total_known_states)

    def compute_bug_detection(self, bugs_found: set[str], bugs_injected: set[str]) -> float:
        """Fraction of injected bugs that were found."""
        if not bugs_injected:
            return 1.0
        if not bugs_found:
            return 0.0
        return len(bugs_found & bugs_injected) / len(bugs_injected)

    def compute_consistency(self, run_traces: list[list[dict]]) -> float:
        """Jaccard similarity of action sequences across multiple runs."""
        if len(run_traces) <= 1:
            return 1.0

        def _actions(trace: list[dict]) -> set[str]:
            return {t["action"] for t in trace if "action" in t}

        action_sets = [_actions(t) for t in run_traces]
        if not any(action_sets):
            return 1.0

        # Average pairwise Jaccard similarity
        total_sim = 0.0
        pairs = 0
        for i in range(len(action_sets)):
            for j in range(i + 1, len(action_sets)):
                a, b = action_sets[i], action_sets[j]
                union = a | b
                if not union:
                    total_sim += 1.0
                else:
                    total_sim += len(a & b) / len(union)
                pairs += 1

        return total_sim / pairs if pairs > 0 else 1.0

    def compute_efficiency(
        self, total_time: float, total_cost: float, scenario_complexity: int = 1
    ) -> float:
        """Efficiency score: higher is better. Penalizes time and cost."""
        complexity_factor = min(max(scenario_complexity, 1), 10) / 5.0
        time_penalty = 1.0 / (1.0 + total_time / 60.0)  # normalize to minutes
        cost_penalty = 1.0 / (1.0 + total_cost)
        return time_penalty * cost_penalty * complexity_factor

    def composite(
        self,
        coverage: float,
        bug_detection: float,
        consistency: float,
        efficiency: float,
    ) -> float:
        """Weighted composite score."""
        return 0.3 * coverage + 0.3 * bug_detection + 0.2 * consistency + 0.2 * efficiency

    def score_run(
        self,
        scenario: dict,
        trace: list[dict],
        costs: dict | None = None,
    ) -> dict:
        """Compute all metrics for a single agent run against a scenario."""
        costs = costs or {}

        states_visited: set[str] = set()
        bugs_found: set[str] = set()

        for step in trace:
            if "state_hash" in step:
                states_visited.add(step["state_hash"])
            if step.get("outcome") == "bug_found":
                bugs_found.add(step.get("action", "unknown"))

        # Known states derived from scenario (simplified: use expected_behavior length as proxy)
        known_states_count = max(len(scenario.get("expected_behavior", "")) // 10, 1)
        known_states = {f"state_{i}" for i in range(known_states_count)}

        bugs_injected = set(scenario.get("failure_conditions", []))

        coverage = self.compute_coverage(states_visited, known_states)
        bug_detection = self.compute_bug_detection(bugs_found, bugs_injected)
        # Consistency requires multiple runs — default to 1.0 for single run
        consistency = 1.0
        efficiency = self.compute_efficiency(
            costs.get("time", 0.0),
            costs.get("cost", 0.0),
            scenario_complexity=costs.get("complexity", 1),
        )

        return {
            "coverage": round(coverage, 4),
            "bug_detection": round(bug_detection, 4),
            "consistency": round(consistency, 4),
            "efficiency": round(efficiency, 4),
            "composite": round(self.composite(coverage, bug_detection, consistency, efficiency), 4),
            "states_visited": len(states_visited),
            "bugs_found": len(bugs_found),
        }
