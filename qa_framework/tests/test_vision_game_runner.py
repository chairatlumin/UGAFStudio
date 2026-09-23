from __future__ import annotations

from qa_framework.vision_game_runner import (
    ActionResult,
    GameScenario,
    PerceptionState,
    VisionGameRunner,
)


def test_game_scenario_creation():
    scenario = GameScenario(
        name="level_1",
        description="First level",
        expected_states=["menu", "playing"],
    )
    assert scenario.name == "level_1"
    assert scenario.description == "First level"
    assert scenario.expected_states == ["menu", "playing"]
    assert scenario.max_steps == 100
    assert scenario.timeout_seconds == 60.0
    assert scenario.tags == []


def test_game_scenario_with_defaults():
    scenario = GameScenario(name="simple", description="test", expected_states=["playing"])
    assert scenario.max_steps == 100
    assert scenario.timeout_seconds == 60.0
    assert scenario.tags == []


def test_perception_state_creation():
    ps = PerceptionState(
        detected_text=["hello"],
        colors_dominant=[(255, 0, 0)],
        scene_classification="menu",
        confidence=0.9,
    )
    assert ps.detected_text == ["hello"]
    assert ps.colors_dominant == [(255, 0, 0)]
    assert ps.scene_classification == "menu"
    assert ps.confidence == 0.9


def test_action_result_creation():
    ar = ActionResult(
        action="jump",
        success=True,
        state_before="idle",
        state_after="jumping",
    )
    assert ar.action == "jump"
    assert ar.success is True
    assert ar.state_before == "idle"
    assert ar.state_after == "jumping"


def test_vision_game_runner_no_scenarios():
    runner = VisionGameRunner()
    results = runner.run_all()
    assert results == []


def test_vision_game_runner_run_scenario():
    runner = VisionGameRunner()

    scenario = GameScenario(
        name="level_1",
        description="First level",
        expected_states=["playing"],
    )

    runner.add_scenario(scenario)

    # Mock perception that immediately reaches expected state
    def perception():
        return PerceptionState(scene_classification="playing")

    # Mock action executor that always succeeds
    def executor(action: str) -> bool:
        return True

    runner.perception_fn = perception
    runner.action_fn = lambda p, s: "start"
    runner.executor_fn = executor

    results = runner.run_all()
    assert len(results) == 1
    assert results[0]["success"] is True
    assert results[0]["steps_taken"] >= 1


def test_vision_game_runner_max_steps():
    runner = VisionGameRunner()

    scenario = GameScenario(
        name="level_1",
        description="First level",
        expected_states=["winning"],
    )

    runner.add_scenario(scenario)

    # Perception never reaches expected state
    def perception():
        return PerceptionState(scene_classification="losing")

    runner.perception_fn = perception

    results = runner.run_all()
    assert len(results) == 1
    assert results[0]["success"] is False
    assert "Max steps" in results[0]["failure_reason"]
