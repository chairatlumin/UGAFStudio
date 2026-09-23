from qa_framework.statistical_runner import StatisticalTestRunner
from qa_framework.vision_game_runner import GameScenario, VisionGameRunner


def test_single_run_pass():
    runner = StatisticalTestRunner(runs=1, pass_threshold=0.8)
    game_runner = VisionGameRunner()
    scenario = GameScenario(name="test", description="test scenario", expected_states=["win"])
    game_runner.add_scenario(scenario)
    report = runner.run(game_runner)
    assert report["runs"] == 1

def test_pass_rate_exceeds_threshold():
    runner = StatisticalTestRunner(runs=10, pass_threshold=0.5)
    game_runner = VisionGameRunner()
    scenario = GameScenario(
        name="always_pass",
        description="always passes",
        expected_states=["stub"],
        max_steps=1,
    )
    game_runner.add_scenario(scenario)
    report = runner.run(game_runner)
    assert report["pass_rate"] >= 0.5

def test_confidence_interval_reported():
    runner = StatisticalTestRunner(runs=5, pass_threshold=0.8)
    game_runner = VisionGameRunner()
    scenario = GameScenario(name="test", description="test", expected_states=["stub"], max_steps=1)
    game_runner.add_scenario(scenario)
    report = runner.run(game_runner)
    assert "confidence_interval" in report
    assert len(report["confidence_interval"]) == 2

def test_below_threshold_fails():
    runner = StatisticalTestRunner(runs=5, pass_threshold=0.99)
    game_runner = VisionGameRunner()
    scenario = GameScenario(
        name="always_fail",
        description="always fails",
        expected_states=["nonexistent"],
        max_steps=1,
    )
    game_runner.add_scenario(scenario)
    report = runner.run(game_runner)
    assert report["pass_rate"] < 0.99
    assert report["passed"] is False
