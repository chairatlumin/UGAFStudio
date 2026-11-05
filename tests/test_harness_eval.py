"""Tests for harness_eval modules — HarnessEval, novelty_check, CLI."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qa_framework.harness_eval.harness import HarnessEval
from qa_framework.harness_eval.novelty_check import check_novelty

# ─── HarnessEval Tests ───

@pytest.fixture
def valid_brief():
    """Write a valid research brief to a temporary file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        brief_path = Path(tmpdir) / "research-test.md"
        brief_path.write_text(
            """# Research Brief: Test Topic — September 2026

## Sources (Perplexity-style synthesis)
- Source One (example.com): https://example.com/one
- Source Two (example.com): https://example.com/two
- Source Three (example.com): https://example.com/three
- Source Four (example.com): https://example.com/four
- Source Five (example.com): https://example.com/five

## Key Findings

### 1. Finding Alpha
Some content here.

### 2. Finding Beta
More content.

## Action Items
- [x] Create research brief
- [x] Review existing briefs for novelty
- [x] Extract key findings
- [ ] Next step

---
Written: 2026-09-24T0530 UTC+7:00 (SE Asia)
"""
        )
        yield brief_path


@pytest.fixture
def invalid_brief():
    """Write an invalid research brief (too few sources, no action items)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        brief_path = Path(tmpdir) / "research-bad.md"
        brief_path.write_text(
            """# Research Brief

## Key Findings
Some content.
"""
        )
        yield brief_path


@pytest.fixture
def valid_plan():
    """Write a valid plan to a temporary file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_path = Path(tmpdir) / "plan-test.md"
        plan_path.write_text(
            """# Plan: Test Component

**Date:** 2026-09-24T0530 UTC+7:00
**Author:** Hermes Auto-Researcher
**Status:** ready

## 1. Problem
The problem statement.

## 2. Solution
The solution description.

## 3. Components
Component list.

## 4. Action Items
- [ ] Implement
- [ ] Test

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Low | Easy |

## 6. Success Metrics
- All tests pass

## 7. Open Questions
- None

## 8. Validation Strategy
```bash
pytest tests/
```

## 9. Implementation Order
1. First
2. Second

---
Written: 2026-09-24T0530 UTC+7:00
"""
        )
        yield plan_path


class TestHarnessEvalValidatesResearchBrief:
    """HarnessEval.validate_research_brief() checks brief structure."""

    def test_valid_brief_passes(self, valid_brief):
        """A well-formed research brief passes validation."""
        evaluator = HarnessEval()
        result = evaluator.validate_research_brief(valid_brief)
        assert result.passed

    def test_invalid_brief_fails(self, invalid_brief):
        """An invalid research brief fails validation."""
        evaluator = HarnessEval()
        result = evaluator.validate_research_brief(invalid_brief)
        assert not result.passed

    def test_brief_has_minimum_sources(self, valid_brief):
        """Brief validation checks for at least 5 sources."""
        evaluator = HarnessEval()
        result = evaluator.validate_research_brief(valid_brief)
        assert result.passed


class TestHarnessEvalValidatesPlan:
    """HarnessEval.validate_plan() checks plan structure."""

    def test_valid_plan_passes(self, valid_plan):
        """A well-formed plan passes validation."""
        evaluator = HarnessEval()
        result = evaluator.validate_plan(valid_plan)
        assert result.passed

    def test_plan_requires_problem_section(self, tmp_path):
        """A plan without Problem section fails."""
        plan_path = tmp_path / "plan-noproblem.md"
        plan_path.write_text("# Plan\n\n## 2. Solution\nContent.")
        evaluator = HarnessEval()
        result = evaluator.validate_plan(plan_path)
        assert not result.passed

    def test_plan_requires_solution_section(self, tmp_path):
        """A plan without Solution section fails."""
        plan_path = tmp_path / "plan-nosolution.md"
        plan_path.write_text("# Plan\n\n## 1. Problem\nContent.")
        evaluator = HarnessEval()
        result = evaluator.validate_plan(plan_path)
        assert not result.passed


class TestNoveltyCheck:
    """check_novelty() detects duplicate research briefs."""

    def test_no_prior_briefs_returns_novel(self, valid_brief):
        """With no prior briefs, any brief is novel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prior_dir = Path(tmpdir) / "prior"
            prior_dir.mkdir()
            is_novel, overlaps = check_novelty(valid_brief, prior_dir)
            assert is_novel
            assert overlaps == []

    def test_duplicate_brief_detected(self, valid_brief):
        """A nearly identical brief is flagged as duplicate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prior_dir = Path(tmpdir) / "prior"
            prior_dir.mkdir()
            # Write a nearly identical brief
            duplicate = prior_dir / "prior-dup.md"
            duplicate.write_text(valid_brief.read_text())
            is_novel, overlaps = check_novelty(valid_brief, prior_dir)
            # Should flag as duplicate (similarity >0.7)
            assert not is_novel
            assert len(overlaps) > 0

    def test_different_brief_returns_novel(self, valid_brief):
        """A clearly different brief is novel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prior_dir = Path(tmpdir) / "prior"
            prior_dir.mkdir()
            different = prior_dir / "prior-different.md"
            different.write_text(
                """# Research Brief: Completely Different Topic — January 2025

## Key Findings
### 1. Quantum Computing Advances
Quantum stuff.

### 2. Blockchain in Supply Chain
Blockchain stuff.
"""
            )
            is_novel, overlaps = check_novelty(valid_brief, prior_dir)
            assert is_novel
            assert overlaps == []
