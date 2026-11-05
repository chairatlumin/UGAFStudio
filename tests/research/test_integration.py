from qa_framework.research.integration import ResearchWorkflow

def test_full_workflow():
    workflow = ResearchWorkflow()
    workflow.record_research_brief("research-001")
    workflow.record_brief_exists("brief-001")
    workflow.record_dispatch("task-001")
    workflow.record_validation_passed("validation-001")
    workflow.record_report("report-001")
    result = workflow.verify()
    assert result.valid

def test_invalid_workflow():
    workflow = ResearchWorkflow()
    workflow.record_dispatch("task-001")
    workflow.record_report("report-001")
    result = workflow.verify()
    assert not result.valid
