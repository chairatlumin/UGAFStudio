"""Tests for FastLoop module."""

from qa_framework.self_healing.fast_loop import FailureClassification, FastLoop
from qa_framework.self_healing.rules_store import RulesStore


def test_classify_permission_denied():
    fl = FastLoop.__new__(FastLoop)
    cls = fl._classify("opencode run: permission denied for path")
    assert cls == FailureClassification.PERMISSION_DENIED


def test_classify_timeout():
    fl = FastLoop.__new__(FastLoop)
    cls = fl._classify("Process timed out after 300 seconds")
    assert cls == FailureClassification.TIMEOUT


def test_classify_verification_failure():
    fl = FastLoop.__new__(FastLoop)
    cls = fl._classify("pytest: 3 failed, 44 passed")
    assert cls == FailureClassification.VERIFICATION_FAILURE


def test_remediate_permission_denied():
    store = RulesStore(":memory:")
    store.add_rule("permission_denied", "rewrite_brief_without_path", "auto")
    fl = FastLoop(store)
    fix = fl._attempt_fix(FailureClassification.PERMISSION_DENIED)
    assert fix["action"] == "rewrite_brief_without_path"
