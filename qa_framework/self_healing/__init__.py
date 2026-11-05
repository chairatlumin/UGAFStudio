from typing import Dict

from qa_framework.self_healing.fast_loop import FailureClassification, FastLoop, RecoveryResult
from qa_framework.self_healing.rules_store import RulesStore

__all__ = [
    "RulesStore",
    "FastLoop",
    "FailureClassification",
    "RecoveryResult",
    "analyze_and_recover",
]


def analyze_and_recover(
    log_text: str, exit_code: int, db_path: str = "self_healing_rules.db"
) -> Dict[str, object]:
    """Entry point for auto-continue cron."""
    store = RulesStore(db_path)
    fl = FastLoop(store)
    result = fl.analyze(log_text, exit_code)
    return {
        "classification": result.classification.value,
        "rule_applied": result.rule_applied,
        "success": result.success,
    }
