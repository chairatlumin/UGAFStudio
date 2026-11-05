from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VerificationResult:
    valid: bool
    failing_step: int | None
    message: str


class ResearchVerifier:
    """Verify that required evidence precedes dispatch and report publication."""

    _KNOWN_EVENTS = frozenset({
        "research_brief_exists", "brief_exists", "dispatch",
        "validation_passed", "report",
    })

    def verify(self, trace: list[str]) -> VerificationResult:
        has_brief = False
        validation_passed = False
        for index, raw_symbol in enumerate(trace):
            symbol = str(raw_symbol)
            if symbol not in self._KNOWN_EVENTS:
                return VerificationResult(
                    False, index, f"Unexpected symbol '{symbol}' at step {index}"
                )
            if symbol in {"research_brief_exists", "brief_exists"}:
                has_brief = True
            elif symbol == "dispatch" and not has_brief:
                return VerificationResult(
                    False, index, "dispatch requires a prior research brief or task brief"
                )
            elif symbol == "validation_passed":
                validation_passed = True
            elif symbol == "report" and not validation_passed:
                return VerificationResult(
                    False, index, "report requires prior successful validation"
                )
        return VerificationResult(True, None, "All contracts satisfied")
