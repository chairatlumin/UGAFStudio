"""Per-run failure detection and rule-based remediation."""

import enum
import re
from dataclasses import dataclass
from typing import Dict, Optional

from qa_framework.self_healing.rules_store import RulesStore


class FailureClassification(enum.Enum):
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    VERIFICATION_FAILURE = "verification_failure"
    SANDBOX_CRASH = "sandbox_crash"
    AGENT_UNHEALTHY = "agent_unhealthy"
    UNKNOWN = "unknown"


@dataclass
class RecoveryResult:
    classification: FailureClassification
    rule_applied: Optional[str]
    success: bool
    retry_brief: Optional[str] = None


class FastLoop:
    PATTERNS = {
        FailureClassification.PERMISSION_DENIED: [
            r"permission\s+denied",
            r"access\s+denied",
            r"EACCES",
        ],
        FailureClassification.TIMEOUT: [
            r"timed?\s+out",
            r"timeout\s+after",
            r"Process\s+timed\s+out",
        ],
        FailureClassification.VERIFICATION_FAILURE: [
            r"pytest:.*failed",
            r"ruff\s+check.*failed",
            r"mypy.*error",
            r"verification\s+gate.*fail",
        ],
        FailureClassification.SANDBOX_CRASH: [
            r"Sandbox.*crash",
            r"subprocess.*error",
            r"OSError.*sandbox",
        ],
    }

    def __init__(self, store: RulesStore) -> None:
        self.store = store

    def _classify(self, log_text: str) -> FailureClassification:
        text_lower = log_text.lower()
        for cls, patterns in self.PATTERNS.items():
            for pat in patterns:
                if re.search(pat, text_lower):
                    return cls
        return FailureClassification.UNKNOWN

    def _attempt_fix(self, classification: FailureClassification) -> Dict[str, object]:
        """Find matching rule and return remediation action."""
        rules = self.store.find_matching_rules({"error_type": classification.value})
        if rules:
            best = rules[0]
            return {"action": best["action"], "rule_id": best["id"]}
        return {"action": None, "rule_id": None}

    def analyze(self, log_text: str, exit_code: int) -> RecoveryResult:
        """Main entry: analyze log output from a run."""
        cls = self._classify(log_text) if exit_code != 0 else FailureClassification.UNKNOWN
        fix = self._attempt_fix(cls)
        rule_applied: Optional[str] = fix["action"] if isinstance(fix["action"], str) else None
        return RecoveryResult(
            classification=cls,
            rule_applied=rule_applied,
            success=rule_applied is not None,
            retry_brief=None,
        )
