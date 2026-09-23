from qa_framework.rail_validator import OutputRAILValidator

VALID_BRIEF = (
    "# TASK\n## Goal\nDo the thing\n## Context\nfile.py\n"
    "## Constraints\nnone\n## Exact Validation Commands\necho ok\n"
    "## Report Format\ntext"
)

MISSING_GOAL_BRIEF = (
    "# TASK\n## Context\nfile.py\n## Constraints\nnone\n"
    "## Exact Validation Commands\necho ok\n## Report Format\ntext"
)

MISSING_CONTEXT_BRIEF = (
    "## Goal\nDo the thing\n## Constraints\nnone\n"
    "## Exact Validation Commands\necho ok\n## Report Format\ntext"
)


def test_valid_brief_passes():
    validator = OutputRAILValidator()
    result = validator.validate(VALID_BRIEF)
    assert result["valid"] is True


def test_missing_goal_fails():
    validator = OutputRAILValidator()
    result = validator.validate(MISSING_GOAL_BRIEF)
    assert result["valid"] is False
    assert "Goal" in result["missing_sections"]


def test_fix_action_adds_defaults():
    validator = OutputRAILValidator(on_fail="fix")
    result = validator.validate(MISSING_CONTEXT_BRIEF)
    assert result["valid"] is False
    assert "fixed" in result
    assert "## Context" in result["brief"]
