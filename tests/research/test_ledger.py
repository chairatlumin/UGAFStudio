from qa_framework.research.ledger import ResearchLedger, Hypothesis, GateResult, FailureConstraint

def test_create_ledger():
    ledger = ResearchLedger()
    assert ledger.hypotheses == []
    assert ledger.gate_outcomes == {}
    assert ledger.failure_constraints == []

def test_add_hypothesis():
    ledger = ResearchLedger()
    h = Hypothesis(id="h1", statement="Test hypothesis", status="active")
    ledger.add_hypothesis(h)
    assert len(ledger.hypotheses) == 1
    assert ledger.hypotheses[0].id == "h1"

def test_record_gate_outcome():
    ledger = ResearchLedger()
    result = GateResult(gate="brief_before_dispatch", passed=True, evidence="brief exists")
    ledger.record_gate_outcome(result)
    assert "brief_before_dispatch" in ledger.gate_outcomes
    assert ledger.gate_outcomes["brief_before_dispatch"].passed

def test_add_failure_constraint():
    ledger = ResearchLedger()
    constraint = FailureConstraint(
        pattern="dispatch_without_brief",
        constraint="brief_exists must precede dispatch",
        source="test_failure"
    )
    ledger.add_failure_constraint(constraint)
    assert len(ledger.failure_constraints) == 1
