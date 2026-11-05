"""Tests for the EvalPipeline — agent evaluation framework."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from qa_framework.eval.agent_scorer import AgentScorer
from qa_framework.eval.eval_runner import EvalRunner
from qa_framework.eval.report_generator import ReportGenerator
from qa_framework.eval.scenario_registry import ScenarioRegistry

# --- Fixtures ---


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_eval.db"


@pytest.fixture
def scenario_reg(db_path: Path) -> ScenarioRegistry:
    return ScenarioRegistry(str(db_path))


@pytest.fixture
def eval_runner(db_path: Path, scenario_reg: ScenarioRegistry) -> EvalRunner:
    return EvalRunner(scenario_reg, AgentScorer(), str(db_path))


@pytest.fixture
def report_gen(db_path: Path, tmp_path: Path) -> ReportGenerator:
    return ReportGenerator(str(db_path), str(tmp_path / "reports"))


def _mock_agent(_: dict) -> list[dict]:
    return [
        {"state_hash": "s1", "action": "move", "outcome": "ok", "reward": 0.1},
        {"state_hash": "s2", "action": "attack", "outcome": "bug_found", "reward": 0.3},
    ]


# --- ScenarioRegistry Tests ---


class TestScenarioRegistry:
    def test_register_and_get(self, scenario_reg: ScenarioRegistry):
        sid = scenario_reg.register(
            "shinebringer",
            "tutorial",
            42,
            "Player completes movement tutorial",
            ["crash_on_load", "stuck_in_wall"],
        )
        assert sid > 0
        sc = scenario_reg.get(sid)
        assert sc["game_id"] == "shinebringer"
        assert sc["level"] == "tutorial"
        assert sc["seed"] == 42
        assert len(sc["failure_conditions"]) == 2

    def test_list_scenarios(self, scenario_reg: ScenarioRegistry):
        scenario_reg.register("game1", "level1", 1, "expected1", ["fc1"])
        scenario_reg.register("game2", "level2", 2, "expected2", ["fc2"])
        scenario_reg.register("game1", "level3", 3, "expected3", ["fc3"])

        all_sc = scenario_reg.list_scenarios()
        assert len(all_sc) == 3

        g1 = scenario_reg.list_scenarios("game1")
        assert len(g1) == 2

    def test_delete(self, scenario_reg: ScenarioRegistry):
        sid = scenario_reg.register("game1", "level1", 1, "expected", ["fc"])
        assert scenario_reg.delete(sid) is True
        with pytest.raises(KeyError):
            scenario_reg.get(sid)

    def test_delete_nonexistent(self, scenario_reg: ScenarioRegistry):
        assert scenario_reg.delete(99999) is False

    def test_versioning(self, scenario_reg: ScenarioRegistry):
        sid1 = scenario_reg.register("g", "l", 1, "e1", ["fc1"], version=1)
        sid2 = scenario_reg.register("g", "l", 1, "e2", ["fc2"], version=2)
        assert sid1 != sid2
        assert scenario_reg.get(sid2)["expected_behavior"] == "e2"

    def test_created_at_timestamp(self, scenario_reg: ScenarioRegistry):
        before = time.time()
        sid = scenario_reg.register("g", "l", 1, "e", ["fc"])
        after = time.time()
        sc = scenario_reg.get(sid)
        assert before <= sc["created_at"] <= after


# --- AgentScorer Tests ---


class TestAgentScorer:
    def setup_method(self):
        self.scorer = AgentScorer()

    def test_coverage_full(self):
        assert self.scorer.compute_coverage({"a", "b", "c"}, {"a", "b", "c"}) == 1.0

    def test_coverage_partial(self):
        result = self.scorer.compute_coverage({"a", "b"}, {"a", "b", "c", "d"})
        assert result == 0.5

    def test_coverage_empty_known(self):
        assert self.scorer.compute_coverage({"a"}, set()) == 1.0

    def test_coverage_empty_visited(self):
        assert self.scorer.compute_coverage(set(), {"a", "b"}) == 0.0

    def test_bug_detection_full(self):
        assert self.scorer.compute_bug_detection({"b1", "b2"}, {"b1", "b2"}) == 1.0

    def test_bug_detection_partial(self):
        result = self.scorer.compute_bug_detection({"b1"}, {"b1", "b2", "b3"})
        assert abs(result - 1 / 3) < 0.001

    def test_bug_detection_no_injected(self):
        assert self.scorer.compute_bug_detection(set(), set()) == 1.0

    def test_bug_detection_none_found(self):
        assert self.scorer.compute_bug_detection(set(), {"b1"}) == 0.0

    def test_consistency_identical(self):
        traces = [
            [{"action": "a"}, {"action": "b"}],
            [{"action": "a"}, {"action": "b"}],
        ]
        assert self.scorer.compute_consistency(traces) == 1.0

    def test_consistency_single_run(self):
        assert self.scorer.compute_consistency([[{"action": "a"}]]) == 1.0

    def test_consistency_empty(self):
        assert self.scorer.compute_consistency([]) == 1.0

    def test_consistency_different(self):
        traces = [
            [{"action": "a"}, {"action": "b"}],
            [{"action": "c"}, {"action": "d"}],
        ]
        result = self.scorer.compute_consistency(traces)
        assert result == 0.0

    def test_consistency_partial_overlap(self):
        traces = [
            [{"action": "a"}, {"action": "b"}],
            [{"action": "a"}, {"action": "c"}],
        ]
        result = self.scorer.compute_consistency(traces)
        # Jaccard: {a,b} ∩ {a,c} = {a} / {a,b,c} = 1/3
        assert abs(result - 1 / 3) < 0.001

    def test_efficiency_normal(self):
        eff = self.scorer.compute_efficiency(60.0, 0.01, 3)
        assert 0.0 <= eff <= 1.0

    def test_efficiency_zero_time_cost(self):
        eff = self.scorer.compute_efficiency(0.0, 0.0, 5)
        assert eff > 0.5  # high efficiency

    def test_composite(self):
        c = self.scorer.composite(1.0, 1.0, 1.0, 1.0)
        assert c == 1.0
        c = self.scorer.composite(0.0, 0.0, 0.0, 0.0)
        assert c == 0.0
        c = self.scorer.composite(0.5, 0.5, 0.5, 0.5)
        assert abs(c - 0.5) < 0.001

    def test_score_run(self):
        scenario = {
            "expected_behavior": "Explore tutorial and defeat first enemy",
            "failure_conditions": ["crash", "stuck"],
        }
        trace = [
            {"state_hash": "s1", "action": "move_forward", "outcome": "moved"},
            {"state_hash": "s2", "action": "attack", "outcome": "bug_found"},
        ]
        result = self.scorer.score_run(scenario, trace, {"time": 30, "cost": 0.005, "complexity": 3})
        assert "coverage" in result
        assert "bug_detection" in result
        assert "consistency" in result
        assert "efficiency" in result
        assert "composite" in result


# --- EvalRunner Tests ---


class TestEvalRunner:
    def test_run_scenario(self, eval_runner: EvalRunner, scenario_reg: ScenarioRegistry):
        sid = scenario_reg.register("g1", "l1", 100, "expected behavior long enough", ["fc1"])
        result = eval_runner.run_scenario(sid, _mock_agent, n_runs=2)
        assert result["scenario_id"] == sid
        assert result["n_runs"] == 2
        assert len(result["scores"]) == 2

    def test_run_batch(self, eval_runner: EvalRunner, scenario_reg: ScenarioRegistry):
        s1 = scenario_reg.register("g1", "l1", 1, "e1", ["fc1"])
        s2 = scenario_reg.register("g2", "l2", 2, "e2 enough", ["fc2"])
        results = eval_runner.run_batch([s1, s2], _mock_agent, n_runs=1)
        assert len(results) == 2

    def test_get_history(self, eval_runner: EvalRunner, scenario_reg: ScenarioRegistry):
        sid = scenario_reg.register("g1", "l1", 1, "e" * 20, ["fc1"])
        eval_runner.run_scenario(sid, _mock_agent, n_runs=3)
        history = eval_runner.get_history(sid)
        assert len(history) == 3
        assert history[0]["scenario_id"] == sid

    def test_record_trace_manually(self, eval_runner: EvalRunner, scenario_reg: ScenarioRegistry):
        sid = scenario_reg.register("g1", "l1", 1, "e" * 20, ["fc1"])
        eval_runner.run_scenario(sid, _mock_agent, n_runs=1)
        history = eval_runner.get_history(sid)
        assert len(history) >= 1


# --- ReportGenerator Tests ---


class TestReportGenerator:
    def test_generate_report(self, report_gen: ReportGenerator, eval_runner: EvalRunner, scenario_reg: ScenarioRegistry):
        sid = scenario_reg.register("g1", "l1", 1, "expected behavior for test scenario long enough", ["crash", "stuck"])
        eval_runner.run_scenario(sid, _mock_agent, n_runs=3)

        output_path = report_gen.generate([sid])
        assert Path(output_path).exists()
        content = Path(output_path).read_text()
        assert "# Evaluation Report" in content
        assert "g1" in content
        assert "l1" in content

    def test_trend_detection(self, report_gen: ReportGenerator, eval_runner: EvalRunner, scenario_reg: ScenarioRegistry):
        sid = scenario_reg.register("g1", "l1", 1, "e" * 30, ["fc"])
        eval_runner.run_scenario(sid, _mock_agent, n_runs=5)
        trend = report_gen.trend(sid)
        assert "sparkline" in trend
        assert "flag" in trend
        assert len(trend["values"]) == 5

    def test_compare_scenarios(self, report_gen: ReportGenerator, eval_runner: EvalRunner, scenario_reg: ScenarioRegistry):
        s1 = scenario_reg.register("g1", "l1", 1, "e" * 20, ["fc1"])
        s2 = scenario_reg.register("g2", "l2", 2, "e" * 20, ["fc2"])
        eval_runner.run_batch([s1, s2], _mock_agent, n_runs=2)

        comparison = report_gen.compare([s1, s2])
        assert s1 in comparison
        assert s2 in comparison
        assert "avg_composite" in comparison[s1]

    def test_sparkline_generation(self, report_gen: ReportGenerator):
        line = report_gen._sparkline([0.1, 0.3, 0.5, 0.7, 0.9])
        assert len(line) == 5
        assert "▁" in line or "█" in line


# --- Integration Tests ---


class TestIntegration:
    def test_full_pipeline(self, db_path: Path, tmp_path: Path):
        reg = ScenarioRegistry(str(db_path))
        runner = EvalRunner(reg, AgentScorer(), str(db_path))
        rep = ReportGenerator(str(db_path), str(tmp_path / "reports"))

        sid = reg.register(
            "shinebringer",
            "tutorial",
            42,
            "Complete movement and combat tutorial sections",
            ["crash_on_start", "input_unresponsive", "texture_corruption"],
        )

        def mock_agent(scenario: dict) -> list[dict]:
            return [
                {"state_hash": f"s{i}", "action": a, "outcome": o, "reward": r}
                for i, (a, o, r) in enumerate([
                    ("start", "ok", 0.0),
                    ("move_north", "ok", 0.1),
                    ("attack_slime", "bug_found", 0.5),
                    ("open_menu", "ok", 0.05),
                ])
            ]

        result = runner.run_scenario(sid, mock_agent, n_runs=3)
        assert result["n_runs"] == 3

        history = runner.get_history(sid)
        assert len(history) == 3

        output = rep.generate([sid])
        content = Path(output).read_text()
        assert "shinebringer" in content

    def test_concurrent_trace_recording(self, db_path: Path):
        import threading

        reg = ScenarioRegistry(str(db_path))
        runner = EvalRunner(reg, AgentScorer(), str(db_path))

        sid = reg.register("g", "l", 1, "e" * 30, ["fc"])
        scenario = reg.get(sid)

        errors: list[str] = []

        def record(run_id: int):
            try:
                for i in range(10):
                    runner.record_trace(run_id, i, f"s{i}", "a", "ok", 0.1)
            except Exception as e:
                errors.append(str(e))

        # Create an initial run to get a run_id
        runner.run_scenario(sid, _mock_agent, n_runs=1)
        history = runner.get_history(sid)
        run_id = history[0]["id"]

        threads = [threading.Thread(target=record, args=(run_id,)) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent errors: {errors}"
