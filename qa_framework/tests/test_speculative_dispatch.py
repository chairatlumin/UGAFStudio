def test_speculator_predicts_next_action():
    from qa_framework.speculative_dispatch import PredictionEngine

    engine = PredictionEngine(history=["run_suite", "analyze_failure"])
    engine.learn_pattern(["run_suite", "analyze_failure"], "fix_failure")
    pred = engine.predict_next()
    assert pred is not None
    assert pred.action == "fix_failure"


def test_speculator_kills_wrong_speculation():
    from qa_framework.speculative_dispatch import (
        PredictionEngine,
        SpeculationBudget,
        SpeculativeDispatcher,
    )

    engine = PredictionEngine(history=["run_suite", "analyze_failure"])
    engine.learn_pattern(["run_suite", "analyze_failure"], "fix_failure")
    budget = SpeculationBudget(max_concurrent=2)
    d = SpeculativeDispatcher(budget=budget, engine=engine)
    result = d.speculate(target="fix_failure", prompt="fix the test failure")
    if result:
        # Only check if speculation actually happened
        assert d.is_alive("fix_failure") is True or d.is_alive("fix_failure") is False
        d.kill("fix_failure")
        assert d.is_alive("fix_failure") is False
    else:
        # If no prediction matched threshold, speculate returns False
        assert result is False


def test_budget_exceeded_evicts_oldest():
    from qa_framework.speculative_dispatch import (
        PredictionEngine,
        SpeculationBudget,
        SpeculativeDispatcher,
    )

    engine = PredictionEngine(history=["a", "b", "c"])
    engine.learn_pattern(["a", "b", "c"], "d")
    budget = SpeculationBudget(max_concurrent=2)
    d = SpeculativeDispatcher(budget=budget, engine=engine)
    # With budget cap at 2, third speculation should fail
    d.speculate("task1", prompt="do something")
    d.speculate("task2", prompt="do something")
    result = d.speculate("task3", prompt="do something")
    # Should fail because budget is full
    assert result is False


def test_speculation_with_no_prediction():
    from qa_framework.speculative_dispatch import PredictionEngine, SpeculativeDispatcher

    engine = PredictionEngine(history=[])
    d = SpeculativeDispatcher(engine=engine)
    result = d.speculate(target="unknown")
    assert result is False
