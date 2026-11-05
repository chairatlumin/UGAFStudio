from __future__ import annotations

import re
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class Finding(NamedTuple):
    rule_id: str
    severity: str  # "low" | "medium" | "high" | "critical"
    description: str
    matched_text: str
    position: tuple[int, int]


class ScanResult(NamedTuple):
    is_safe: bool
    findings: list[Finding]
    risk_score: float          # 0.0-1.0
    action: str                # "allow" | "sanitize" | "block"


# ---------------------------------------------------------------------------
# Rule set
# ---------------------------------------------------------------------------

DEFAULT_RULES: list[dict] = [
    # ── Prompt Injection – direct ────────────────────────────────────────
    {"id": "PI-001", "severity": "high",
     "pattern": r"ignore\s+(previous|all|above)\s+instructions?"},
    {"id": "PI-002", "severity": "high",
     "pattern": r"you\s+are\s+now"},
    {"id": "PI-003", "severity": "high",
     "pattern": r"new\s+instructions?\s*[:=]"},
    {"id": "PI-004", "severity": "high",
     "pattern": r"system\s+prompt"},
    {"id": "PI-005", "severity": "high",
     "pattern": r"override\s+(previous|all|safety|guardrails?)"},
    # ── Prompt Injection – indirect (obfuscation) ────────────────────────
    {"id": "PI-006", "severity": "medium",
     "pattern": r"[\u200b-\u200f\u2060-\u2064]"},          # zero-width unicode
    {"id": "PI-007", "severity": "medium",
     "pattern": r"[A-Za-z0-9+/]{30,}={0,2}"},              # base64 blobs
    # ── PII leaks ───────────────────────────────────────────────────────
    {"id": "PII-001", "severity": "medium",
     "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"},
    {"id": "PII-002", "severity": "medium",
     "pattern": r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"},          # SSN-like
    {"id": "PII-003", "severity": "low",
     "pattern": r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"},      # phone-like
    # ── Exfiltration ────────────────────────────────────────────────────
    {"id": "EXF-001", "severity": "high",
     "pattern": r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"},
    {"id": "EXF-002", "severity": "critical",
     "pattern": r"[a-zA-Z0-9+/]{200,}={0,2}"},             # large base64
    {"id": "EXF-003", "severity": "medium",
     "pattern": r"https?://[^\s]*\.(xyz|top|gq|ml|cf|tk|pw)"},
]

_SEVERITY_SCORE = {"low": 0.1, "medium": 0.3, "high": 0.6, "critical": 1.0}

# Block threshold: a single high-severity finding (direct injection) = block
_BLOCK_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# IntentScanner
# ---------------------------------------------------------------------------

class IntentScanner:
    """Scan agent output for prompt injection, PII leaks, exfiltration."""

    def __init__(self, rules_path: str | None = None) -> None:
        self.rules: list[dict] = list(DEFAULT_RULES)
        if rules_path:
            self.load_rules(rules_path)

    # ── public API ──────────────────────────────────────────────────────

    def scan(self, text: str) -> ScanResult:
        findings: list[Finding] = []
        for rule in self.rules:
            for m in re.finditer(rule["pattern"], text, re.IGNORECASE):
                findings.append(Finding(
                    rule_id=rule["id"],
                    severity=rule["severity"],
                    description=f"Matched rule {rule['id']}: {rule['pattern']}",
                    matched_text=m.group()[:80],            # cap length
                    position=(m.start(), m.end()),
                ))

        risk_score = min(1.0, sum(_SEVERITY_SCORE[f.severity] for f in findings))

        if risk_score >= _BLOCK_THRESHOLD:
            action = "block"
        elif risk_score >= 0.3:
            action = "sanitize"
        else:
            action = "allow"

        return ScanResult(
            is_safe=(action == "allow"),
            findings=findings,
            risk_score=round(risk_score, 2),
            action=action,
        )

    def scan_agent_output(self, agent_id: str, output: str) -> ScanResult:
        """Thunk for bridge integration — currently just delegates to scan()."""
        return self.scan(output)

    def load_rules(self, path: str) -> None:
        import json
        with open(path, encoding="utf-8") as fh:
            extra = json.load(fh)
        if not isinstance(extra, list):
            raise ValueError("Rules file must contain a JSON list")
        self.rules.extend(extra)
