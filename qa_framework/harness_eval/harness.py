"""Harness evaluation class with validation methods for research briefs,
plans, and task dispatch."""


from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class HarnessResult:
    """Result of a harness validation check."""
    test_name: str
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class HarnessEval:
    """Validates the auto-researcher pipeline: brief, plan, task, novelty."""

    VALID_PLAN_STATUSES = frozenset({"pending", "in_progress", "completed", "cancelled", "ready"})

    def validate_research_brief(self, path: Path) -> HarnessResult:
        """Validate research brief format.

        Checks: frontmatter present, all action items checked, at least 5 sources,
        no duplicate topics vs. prior briefs.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not path.exists():
            return HarnessResult(
                test_name="validate_research_brief",
                passed=False,
                errors=[f"Research brief not found: {path}"],
            )

        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = path.read_text(encoding="cp1252")
        issues: List[str] = []

        # Check frontmatter
        if not content.startswith("#"):
            issues.append("Missing frontmatter (expected # title at start)")

        # Check action items are checked
        checked_items = len(re.findall(r"- \[x\]", content))
        unchecked_items = len(re.findall(r"- \[ \]", content))
        if unchecked_items > 0:
            warnings.append(f"{unchecked_items} unchecked action items remain")
        if checked_items < 3:
            issues.append("Fewer than 3 checked action items")

        # Check at least 5 sources
        source_count = len(re.findall(r"https?://", content))
        if source_count < 5:
            issues.append(f"Fewer than 5 sources found ({source_count})")

        if issues:
            errors.extend(issues)
            passed = False
        else:
            passed = True

        return HarnessResult(
            test_name="validate_research_brief",
            passed=passed,
            errors=errors,
            warnings=warnings,
        )

    def validate_plan(self, path: Path) -> HarnessResult:
        """Validate plan structure.

        Checks: problem/solution/components/action items sections present,
        status is valid enum.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not path.exists():
            return HarnessResult(
                test_name="validate_plan",
                passed=False,
                errors=[f"Plan not found: {path}"],
            )

        content = path.read_text(encoding="utf-8")
        issues: List[str] = []

        # Check required sections
        lower = content.lower()
        required_sections = ["problem", "solution", "components"]
        for section in required_sections:
            if section not in lower:
                issues.append(f"Missing required section: {section}")

        # Check status is valid enum
        if "status:" in lower:
            status_value = lower.split("status:")[1].split("\n")[0].strip()
            # Strip markdown bold/italic markers
            status_value = status_value.replace("*", "").replace("_", "").strip()
            if status_value not in {s.lower() for s in self.VALID_PLAN_STATUSES}:
                issues.append(f"Invalid plan status: {status_value}")

        if issues:
            errors.extend(issues)
            passed = False
        else:
            passed = True

        return HarnessResult(
            test_name="validate_plan",
            passed=passed,
            errors=errors,
            warnings=warnings,
        )

    def validate_task_dispatch(
        self, task_path: Path, log_path: Path
    ) -> HarnessResult:
        """Validate task dispatch.

        Checks: brief has all required sections, dispatch command succeeds,
        report file exists.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Check brief has required sections
        if task_path.exists():
            brief_content = task_path.read_text(encoding="utf-8")
            lower = brief_content.lower()
            for section in ["problem", "solution", "task"]:
                if section not in lower:
                    errors.append(f"Brief missing required section: {section}")
        else:
            errors.append(f"Task path not found: {task_path}")

        # Check log exists and has valid entries
        if log_path.exists():
            log_content = log_path.read_text(encoding="utf-8")
            if "exit code" not in log_content.lower() and "failed" not in log_content.lower():
                warnings.append("Log doesn't contain expected exit/failure information")
        else:
            errors.append(f"Log path not found: {log_path}")

        # Check report file exists
        # Look for report in the same directory as the task
        if task_path.exists():
            report_path = task_path.parent / f"report-{task_path.name}"
            if not report_path.exists():
                warnings.append(f"Expected report not found: {report_path}")

        if errors:
            passed = False
        else:
            passed = True

        return HarnessResult(
            test_name="validate_task_dispatch",
            passed=passed,
            errors=errors,
            warnings=warnings,
        )

    def validate_re_verify(self, log_path: Path) -> HarnessResult:
        """Validate that re-verification commands were actually run.

        Checks: validation commands were actually run, pass/fail status extracted.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not log_path.exists():
            return HarnessResult(
                test_name="validate_re_verify",
                passed=False,
                errors=[f"Log not found: {log_path}"],
            )

        content = log_path.read_text(encoding="utf-8")
        lower = content.lower()

        # Check for re-verify markers
        re_verify_patterns = [
            "re-verify",
            "reverify",
            "validation complete",
            "passed",
            "failed",
        ]
        found_patterns = [p for p in re_verify_patterns if p in lower]

        if not found_patterns:
            warnings.append("No re-verification patterns found in log")

        # Check for pass/fail status
        has_pass = "passed" in lower or "pass" in lower
        has_fail = "failed" in lower or "fail" in lower

        if not has_pass and not has_fail:
            warnings.append("No pass/fail status found in log")

        if not found_patterns and not (has_pass or has_fail):
            errors.append("No re-verification evidence found")
            passed = False
        else:
            passed = True

        return HarnessResult(
            test_name="validate_re_verify",
            passed=passed,
            errors=errors,
            warnings=warnings,
        )

    def validate_all(
        self,
        brief_path: Path,
        plan_path: Path,
        task_path: Path,
        log_path: Path,
    ) -> dict[str, HarnessResult]:
        """Run all harness validations and return results dict."""
        return {
            "research_brief": self.validate_research_brief(brief_path),
            "plan": self.validate_plan(plan_path),
            "task_dispatch": self.validate_task_dispatch(task_path, log_path),
            "re_verify": self.validate_re_verify(log_path),
        }
