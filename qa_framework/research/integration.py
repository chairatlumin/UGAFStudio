# qa_framework/research/integration.py
from typing import List
from qa_framework.research.ledger import ResearchLedger, EvidenceRef, GateResult
from qa_framework.research.verifier import ResearchVerifier, VerificationResult

class ResearchWorkflow:
    def __init__(self, ledger_path: str = ".ai/research/ledger.json"):
        self.ledger = ResearchLedger.load(ledger_path)
        self.verifier = ResearchVerifier()
        self.trace: List[str] = []
    
    def record_research_brief(self, brief_id: str):
        self.ledger.add_evidence(EvidenceRef(
            id=brief_id,
            type="research_brief",
            path=f".ai/research/{brief_id}.md"
        ))
        self.trace.append("research_brief_exists")
    
    def record_brief_exists(self, brief_id: str):
        self.ledger.add_evidence(EvidenceRef(
            id=brief_id,
            type="brief",
            path=f".ai/a2a/tasks/{brief_id}.md"
        ))
        self.trace.append("brief_exists")
    
    def record_dispatch(self, task_id: str):
        self.ledger.record_trajectory("dispatch", {"task_id": task_id})
        self.trace.append("dispatch")
    
    def record_validation_passed(self, validation_id: str):
        self.ledger.record_gate_outcome(GateResult(
            gate="validation",
            passed=True,
            evidence=validation_id
        ))
        self.trace.append("validation_passed")
    
    def record_report(self, report_id: str):
        self.ledger.add_evidence(EvidenceRef(
            id=report_id,
            type="report",
            path=f".ai/a2a/tasks/{report_id}.md"
        ))
        self.trace.append("report")
    
    def verify(self) -> VerificationResult:
        return self.verifier.verify(self.trace)
    
    def save(self):
        self.ledger.save()
