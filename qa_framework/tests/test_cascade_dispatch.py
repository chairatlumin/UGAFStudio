from qa_framework.cascade_dispatch import CascadeDispatchRouter, EscalationPolicy


def test_default_policy_no_escalation_on_success():
    policy = EscalationPolicy()
    assert not policy.should_escalate("valid output here", "free-model")

def test_empty_content_triggers_escalation():
    policy = EscalationPolicy()
    assert policy.should_escalate("", "free-model")

def test_json_parse_failure_escalates():
    policy = EscalationPolicy(require_json=True)
    assert policy.should_escalate("not json", "free-model")

def test_router_first_dispatch_uses_cheapest_model():
    router = CascadeDispatchRouter(models=["free-a", "paid-b", "premium-c"])
    assert router.current_model == "free-a"

def test_router_escalates_on_bad_output():
    router = CascadeDispatchRouter(
        models=["free-a", "paid-b"],
        policy=EscalationPolicy(max_consecutive_failures=1),
    )
    router.record_result("free-a", "")
    assert router.current_model == "paid-b"

def test_router_resets_after_success():
    router = CascadeDispatchRouter(models=["free-a", "paid-b"])
    router.record_result("free-a", "")
    router.record_result("paid-b", "good output")
    assert router.current_model == "free-a"

def test_cost_tracking():
    router = CascadeDispatchRouter(models=["free", "paid"])
    router.record_result("free", "output")
    report = router.cost_report()
    assert report["total_dispatches"] == 1
    assert report["escalation_count"] == 0

def test_fallback_on_connection_error():
    router = CascadeDispatchRouter(models=["free-a", "paid-b"])
    router.record_connection_error("free-a")
    assert router.current_model == "paid-b"
