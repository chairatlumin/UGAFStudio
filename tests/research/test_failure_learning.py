from qa_framework.research.failure_learning import FailureLearner

def test_record_failure():
    learner = FailureLearner()
    learner.record_failure("dispatch_without_brief", "brief_exists must precede dispatch")
    assert len(learner.constraints) == 1

def test_check_constraint():
    learner = FailureLearner()
    learner.record_failure("dispatch_without_brief", "brief_exists must precede dispatch")
    assert learner.violates_constraint(["dispatch", "report"])
    assert not learner.violates_constraint(["brief_exists", "dispatch", "report"])
