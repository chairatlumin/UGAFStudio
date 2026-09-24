"""Tests for ToolResultValidator."""
from __future__ import annotations

from qa_framework.tool_result_validator import ToolResultValidator


class TestToolResultValidator:
    def test_validate_json_schema_pass(self) -> None:
        validator = ToolResultValidator()
        schema = {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        }
        result = validator.validate('{"status": "ok"}', schema=schema)
        assert result.is_valid

    def test_validate_json_schema_fail(self) -> None:
        validator = ToolResultValidator()
        schema = {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        }
        result = validator.validate('{"foo": "bar"}', schema=schema)
        assert not result.is_valid

    def test_sanitize_text_strips_control_chars(self) -> None:
        validator = ToolResultValidator()
        text = "Hello\x00World\x07Test"
        result = validator.sanitize_text(text)
        assert "\x00" not in result
        assert "\x07" not in result
        assert "Hello" in result

    def test_validate_invalid_json(self) -> None:
        validator = ToolResultValidator()
        result = validator.validate("not json at all")
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validate_type_mismatch(self) -> None:
        validator = ToolResultValidator()
        schema = {
            "type": "object",
            "properties": {"count": {"type": "number"}},
            "required": ["count"],
        }
        result = validator.validate('{"count": "not_a_number"}', schema=schema)
        assert not result.is_valid
        assert any("expected number" in e for e in result.errors)

    def test_validate_min_max_bounds(self) -> None:
        validator = ToolResultValidator()
        schema = {
            "type": "object",
            "properties": {"score": {"type": "number", "minimum": 0.0, "maximum": 1.0}},
            "required": ["score"],
        }
        result_valid = validator.validate('{"score": 0.5}', schema=schema)
        assert result_valid.is_valid
        result_invalid = validator.validate('{"score": 1.5}', schema=schema)
        assert not result_invalid.is_valid

    def test_tripwire_triggers_on_many_errors(self) -> None:
        validator = ToolResultValidator()
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "string"},
                "c": {"type": "string"},
            },
            "required": ["a", "b", "c"],
        }
        result = validator.validate('{"x": 1}', schema=schema)
        assert result.tripwire_triggered

    def test_sanitize_text_preserves_whitespace(self) -> None:
        validator = ToolResultValidator()
        text = "Line1\nLine2\tTabbed"
        result = validator.sanitize_text(text)
        assert "\n" in result
        assert "\t" in result

    def test_sanitize_text_truncates_long_input(self) -> None:
        validator = ToolResultValidator(max_text_length=10)
        text = "A" * 20
        result = validator.sanitize_text(text)
        assert len(result) == 22
        assert "[TRUNCATED]" in result

    def test_validate_no_schema_just_parses(self) -> None:
        validator = ToolResultValidator()
        result = validator.validate('{"any": "data"}')
        assert result.is_valid
        assert result.sanitized_value == {"any": "data"}
