from qa_framework.research.verifier import ResearchVerifier

def test_verify_valid_workflow():
    verifier = ResearchVerifier()
    trace = ["research_brief_exists", "brief_exists", "dispatch", "validation_passed", "report"]
    result = verifier.verify(trace)
    assert result.valid

def test_verify_invalid_workflow():
    verifier = ResearchVerifier()
    trace = ["dispatch", "report"]
    result = verifier.verify(trace)
    assert not result.valid
