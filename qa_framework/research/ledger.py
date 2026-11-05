# qa_framework/research/ledger.py
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
import json

@dataclass
class Hypothesis:
    id: str
    statement: str
    status: str  # "active", "validated", "refuted", "abandoned"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    evidence: List[str] = field(default_factory=list)

@dataclass
class GateResult:
    gate: str
    passed: bool
    evidence: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class FailureConstraint:
    pattern: str
    constraint: str
    source: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class EvidenceRef:
    id: str
    type: str  # "research_brief", "validation_result", "report"
    path: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

class ResearchLedger:
    def __init__(self, path: str = ".ai/research/ledger.json"):
        self.path = path
        self.hypotheses: List[Hypothesis] = []
        self.gate_outcomes: Dict[str, GateResult] = {}
        self.failure_constraints: List[FailureConstraint] = []
        self.evidence_pointers: Dict[str, EvidenceRef] = {}
        self.research_trajectory: List[Dict[str, Any]] = []
    
    def add_hypothesis(self, hypothesis: Hypothesis):
        self.hypotheses.append(hypothesis)
    
    def record_gate_outcome(self, result: GateResult):
        self.gate_outcomes[result.gate] = result
    
    def add_failure_constraint(self, constraint: FailureConstraint):
        self.failure_constraints.append(constraint)
    
    def add_evidence(self, ref: EvidenceRef):
        self.evidence_pointers[ref.id] = ref
    
    def record_trajectory(self, event: str, metadata: Dict[str, Any] = None):
        self.research_trajectory.append({
            "event": event,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        })
    
    def save(self):
        data = {
            "hypotheses": [asdict(h) for h in self.hypotheses],
            "gate_outcomes": {k: asdict(v) for k, v in self.gate_outcomes.items()},
            "failure_constraints": [asdict(c) for c in self.failure_constraints],
            "evidence_pointers": {k: asdict(v) for k, v in self.evidence_pointers.items()},
            "research_trajectory": self.research_trajectory,
        }
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: str = ".ai/research/ledger.json") -> "ResearchLedger":
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            ledger = cls(path)
            ledger.hypotheses = [Hypothesis(**h) for h in data.get("hypotheses", [])]
            ledger.gate_outcomes = {k: GateResult(**v) for k, v in data.get("gate_outcomes", {}).items()}
            ledger.failure_constraints = [FailureConstraint(**c) for c in data.get("failure_constraints", [])]
            ledger.evidence_pointers = {k: EvidenceRef(**v) for k, v in data.get("evidence_pointers", {}).items()}
            ledger.research_trajectory = data.get("research_trajectory", [])
            return ledger
        except FileNotFoundError:
            return cls(path)
