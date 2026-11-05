"""Tests for RulesStore module."""

from qa_framework.self_healing.rules_store import RulesStore


def test_add_and_query_rule():
    store = RulesStore(":memory:")
    store.add_rule("permission_denied", "rewrite_brief_without_path", "auto", confidence=0.8)
    rules = store.find_matching_rules({"error_type": "permission_denied"})
    assert len(rules) == 1
    assert rules[0]["action"] == "rewrite_brief_without_path"


def test_confidence_decay():
    store = RulesStore(":memory:")
    store.add_rule("timeout", "increase_timeout", "auto", confidence=0.9)
    store.fire_rule(1)
    rule = store.get_rule(1)
    assert rule["confidence"] > 0.9


def test_stale_rule_pruning():
    store = RulesStore(":memory:")
    store.add_rule("old_pattern", "noop", "auto", confidence=0.1)
    store.prune_stale(max_age_days=0)
    assert store.count_rules() == 0


def test_confidence_feedback():
    store = RulesStore(":memory:")
    store.add_rule("verify_fail", "rerun_tests", "auto", confidence=0.5)
    store.record_outcome(1, success=False)
    rule = store.get_rule(1)
    assert rule["confidence"] < 0.5
