from __future__ import annotations

from qa_framework.a2a_adapter import (
    A2AAdapter,
    A2ATask,
    A2ATaskState,
    AdaptiveModelRouter,
    ConfidenceScorer,
    ConsensusDispatcher,
    SelfVerifyingOutput,
    VerificationContext,
)


def test_a2a_task_lifecycle():
    task = A2ATask(id="t1", prompt="run suite", agent="opencode")
    assert task.state == A2ATaskState.SUBMITTED
    task.mark_working()
    assert task.state == A2ATaskState.WORKING
    task.mark_completed(output="done")
    assert task.state == A2ATaskState.COMPLETED


def test_a2a_task_failure():
    task = A2ATask(id="t2", prompt="run", agent="opencode")
    task.mark_failed("timeout")
    assert task.state == A2ATaskState.FAILED
    assert task.error == "timeout"


def test_a2a_adapter_submit_returns_task_id():
    adapter = A2AAdapter(opencode_url="http://127.0.0.1:4096")
    task = adapter.submit_task(prompt="analyze UGAFStudio", agent="opencode")
    assert task.id.startswith("a2a-")
    assert task.state in (A2ATaskState.SUBMITTED, A2ATaskState.WORKING)


def test_a2a_adapter_get_and_cancel():
    adapter = A2AAdapter(opencode_url="http://127.0.0.1:4096")
    task = adapter.submit_task(prompt="test", agent="opencode")
    fetched = adapter.get_task(task.id)
    assert fetched is not None
    assert fetched.id == task.id
    assert adapter.cancel_task(task.id) is True


# === Verification Layer Tests ===


def test_verification_context_creation():
    vc = VerificationContext(
        expected_output_format="markdown",
        must_contain=["summary", "commands"],
        must_not_contain=["TODO", "FIXME"],
        validation_commands=["ruff check ."],
    )
    assert vc.expected_output_format == "markdown"
    assert "summary" in vc.must_contain


def test_verification_context_check_passes():
    vc = VerificationContext(
        must_contain=["## Confidence", "## Issues"],
        must_not_contain=["TODO", "FIXME"],
    )
    text = "## Confidence: 0.9\n## Issues:\n- all clear\n- no blockers"
    ok, failures = vc.check_output(text)
    assert ok, f"Should pass: {failures}"
    assert len(failures) == 0


def test_verification_context_check_fails_on_missing():
    vc = VerificationContext(must_contain=["## Confidence"])
    text = "## Issues:\n- missing confidence section"
    ok, failures = vc.check_output(text)
    assert not ok
    assert any("Missing required term" in f for f in failures)


def test_verification_context_check_fails_on_forbidden():
    vc = VerificationContext(must_not_contain=["TODO", "FIXME"])
    text = "TODO: finish this\nFIXME: broken"
    ok, failures = vc.check_output(text)
    assert not ok
    assert sum(1 for f in failures if "Forbidden term found" in f) == 2


def test_confidence_scorer_records_outcome():
    scorer = ConfidenceScorer()
    scorer.record("opencode/nemotron-3.5", "code_generation", True)
    scorer.record("opencode/nemotron-3.5", "code_generation", True)
    scorer.record("opencode/nemotron-3.5", "code_generation", False)
    score = scorer.get_score("opencode/nemotron-3.5", "code_generation")
    assert 0.0 <= score <= 1.0
    assert abs(score - 0.666) < 0.01


def test_confidence_scorer_neutral_when_unknown():
    scorer = ConfidenceScorer()
    assert scorer.get_score("unknown-model", "unknown-task") == 0.5


def test_confidence_scorer_best_model():
    scorer = ConfidenceScorer()
    scorer.record("model-a", "test_gen", True)
    scorer.record("model-a", "test_gen", True)
    scorer.record("model-a", "test_gen", True)
    scorer.record("model-b", "test_gen", True)
    scorer.record("model-b", "test_gen", False)
    best = scorer.best_model("test_gen", ["model-a", "model-b"])
    assert best == "model-a"


def test_confidence_scorer_calibration_report():
    scorer = ConfidenceScorer()
    scorer.record("model-a", "task1", True)
    scorer.record("model-a", "task1", False)
    report = scorer.calibration_report()
    assert "model-a" in report
    assert "task1" in report["model-a"]
    assert report["model-a"]["task1"] == 0.5


def test_self_verifying_output_parse():
    text = (
        "## Summary\n"
        "Done\n"
        "## Confidence: 0.85\n"
        "## Issues:\n"
        "- issue: none\n"
        "## Self-Check:\n"
        "- format ok"
    )
    svo = SelfVerifyingOutput.parse(text)
    assert svo.confidence == 0.85
    assert any("none" in i for i in svo.issues)


def test_self_verifying_output_confidence_clamped():
    text = "## Confidence: 1.5"
    svo = SelfVerifyingOutput.parse(text)
    assert svo.confidence == 1.0

    text_neg = "## Confidence: -0.3"
    svo_neg = SelfVerifyingOutput.parse(text_neg)
    assert svo_neg.confidence == 0.0


def test_self_verifying_output_high_confidence():
    svo = SelfVerifyingOutput(confidence=0.85)
    assert svo.is_high_confidence()
    assert not svo.is_high_confidence(threshold=0.9)


def test_self_verifying_output_has_blockers():
    svo_ok = SelfVerifyingOutput(confidence=0.9, issues=[])
    assert not svo_ok.has_blockers()

    svo_blocked = SelfVerifyingOutput(confidence=0.4, issues=["missing tests"])
    assert svo_blocked.has_blockers()


def test_consensus_dispatcher_builds_brief():
    dispatcher = ConsensusDispatcher(
        opencode_url="http://127.0.0.1:4096",
        models=["opencode/nemotron-3.5-lightning-free"],
        timeout=60,
    )
    vc = VerificationContext(expected_output_format="markdown", must_contain=["summary"])
    brief = dispatcher._build_brief("test goal", "test context", ["ruff"], vc)
    assert "## Self-Verifying Output" in brief
    assert "summary" in brief
    assert "## Constraints" in brief
    assert "## Must Contain" in brief


def test_consensus_dispatcher_merge_single_result():
    dispatcher = ConsensusDispatcher()
    task = A2ATask(id="t1", prompt="x", agent="a")
    task.mark_completed("output text")
    best, conf = dispatcher.merge_results([task])
    assert best == "output text"
    assert conf == 0.5


def test_consensus_dispatcher_merge_multiple_agreeing():
    dispatcher = ConsensusDispatcher()
    t1 = A2ATask(id="t1", prompt="x", agent="a")
    t2 = A2ATask(id="t2", prompt="x", agent="a")
    t1.mark_completed("line1\nline2\nline3\nunique_a")
    t2.mark_completed("line1\nline2\nline3\nunique_b")
    best, conf = dispatcher.merge_results([t1, t2])
    assert "line1" in best
    assert "line2" in best
    assert "line3" in best
    assert conf > 0.5  # high agreement → boosted confidence


def test_consensus_dispatcher_merge_empty():
    dispatcher = ConsensusDispatcher()
    best, conf = dispatcher.merge_results([])
    assert best == ""
    assert conf == 0.0


def test_adaptive_model_router_selects_best():
    scorer = ConfidenceScorer()
    scorer.record("model-a", "test_gen", True)
    scorer.record("model-a", "test_gen", True)
    scorer.record("model-b", "test_gen", True)
    scorer.record("model-b", "test_gen", False)
    scorer.record("model-b", "test_gen", False)
    router = AdaptiveModelRouter(scorer)
    best = router.select_model("test_gen", ["model-a", "model-b"])
    assert best == "model-a"


def test_adaptive_model_router_fallback():
    scorer = ConfidenceScorer()
    router = AdaptiveModelRouter(scorer, fallback_model="default-model")
    assert router.select_model("unknown", []) == "default-model"


def test_adaptive_model_router_classify_task_type():
    scorer = ConfidenceScorer()
    router = AdaptiveModelRouter(scorer)

    assert router.classify_task_type("Run QA test suite") == "qa_runner"
    assert router.classify_task_type("Review this code") == "code_review"
    assert router.classify_task_type("Fix the bug in login") == "bug_fix"
    assert router.classify_task_type("Update documentation") == "documentation"
    assert router.classify_task_type("Refactor this module") == "refactoring"
    assert router.classify_task_type("Add a new feature") == "code_generation"


def test_full_verification_pipeline():
    """Integration test: all components work together."""
    # Create verification context
    vc = VerificationContext(
        expected_output_format="markdown",
        must_contain=["## Confidence"],
        must_not_contain=["TODO", "FIXME"],
        validation_commands=["python -m pytest"],
    )

    # Self-check pass
    ok, failures = vc.check_output("## Confidence: 0.9\nSummary done")
    assert ok, f"Self-check should pass: {failures}"

    # Self-check fail on forbidden terms
    vc_forbidden = VerificationContext(must_not_contain=["TODO", "FIXME"])
    bad_ok, bad_failures = vc_forbidden.check_output("TODO: implement\nFIXME: fix this")
    assert not bad_ok
    assert len(bad_failures) == 2

    # Parse self-verifying output
    svo = SelfVerifyingOutput.parse("## Confidence: 0.85\n## Issues:\n- none")
    assert svo.confidence == 0.85

    # Scorer and router
    scorer = ConfidenceScorer()
    scorer.record("model-a", "code_gen", True)
    scorer.record("model-a", "code_gen", True)
    scorer.record("model-b", "code_gen", False)
    router = AdaptiveModelRouter(scorer)
    best = router.select_model("code_gen", ["model-a", "model-b"])
    assert best == "model-a"

    # Dispatcher brief includes verification context
    dispatcher = ConsensusDispatcher(models=["model-a", "model-b"])
    brief = dispatcher._build_brief("test goal", "context here", ["pytest"], vc)
    assert "## Self-Verifying Output" in brief
    assert "## Must Contain" in brief
