from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class OutputRAILValidator:
    """Validates A2A task briefs against required schema sections."""
    required_sections: list[str] = field(default_factory=lambda: [
        "Goal", "Context", "Constraints", "Exact Validation Commands", "Report Format"
    ])
    on_fail: Literal["reject", "fix"] = "reject"

    def validate(self, brief: str) -> dict:
        missing = []
        for section in self.required_sections:
            pattern = rf"##\s+{re.escape(section)}\s*\n"
            if not re.search(pattern, brief):
                missing.append(section)
        if not missing:
            return {"valid": True, "missing_sections": [], "brief": brief}
        if self.on_fail == "fix":
            fixed = self._add_defaults(brief, missing)
            return {"valid": False, "missing_sections": missing, "brief": fixed, "fixed": True}
        return {"valid": False, "missing_sections": missing, "brief": brief}

    def _add_defaults(self, brief: str, missing: list[str]) -> str:
        result = brief
        defaults = {
            "Context": "## Context\nNo specific context provided.\n",
            "Constraints": "## Constraints\nNo specific constraints.\n",
            "Exact Validation Commands": "## Exact Validation Commands\necho 'no validation'\n",
            "Report Format": "## Report Format\nFree-form text.\n",
            "Goal": "## Goal\nNo goal specified.\n",
        }
        for section in missing:
            if section in defaults:
                result += "\n" + defaults[section]
        return result
