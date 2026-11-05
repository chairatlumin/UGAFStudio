# qa_framework/research/failure_learning.py
from typing import List, Dict
from qa_framework.research.ledger import FailureConstraint

class FailureLearner:
    def __init__(self):
        self.constraints: List[FailureConstraint] = []
        self.failure_patterns: Dict[str, int] = {}
    
    def record_failure(self, pattern: str, constraint: str):
        self.constraints.append(FailureConstraint(
            pattern=pattern,
            constraint=constraint,
            source="failure_learning"
        ))
        self.failure_patterns[pattern] = self.failure_patterns.get(pattern, 0) + 1
    
    def violates_constraint(self, trace: List[str]) -> bool:
        """Check if trace violates any recorded constraint."""
        for constraint in self.constraints:
            if constraint.pattern == "dispatch_without_brief":
                if "dispatch" in trace and "brief_exists" not in trace:
                    return True
        return False
    
    def get_common_failures(self, top_n: int = 5) -> List[tuple]:
        """Get most common failure patterns."""
        sorted_patterns = sorted(
            self.failure_patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_patterns[:top_n]
