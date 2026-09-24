"""Structured tool result validation and sanitization."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]
    tripwire_triggered: bool = False
    sanitized_value: Any = None


class ToolResultValidator:
    """Validate tool outputs and sanitize text."""

    def __init__(self, max_text_length: int = 100_000) -> None:
        self._max_length = max_text_length

    def validate_json(self, raw: str) -> ValidationResult:
        """Parse and validate JSON string."""
        try:
            data = json.loads(raw)
            return ValidationResult(is_valid=True, errors=[], sanitized_value=data)
        except json.JSONDecodeError as e:
            return ValidationResult(is_valid=False, errors=[str(e)], tripwire_triggered=False)

    def validate(self, raw: str, schema: dict[str, Any] | None = None) -> ValidationResult:
        """Validate JSON string against a simple schema."""
        parse_result = self.validate_json(raw)
        if not parse_result.is_valid:
            return parse_result

        data = parse_result.sanitized_value
        if schema is None:
            return parse_result

        errors: list[str] = []
        tripwire = False

        # Check required fields
        required = schema.get("required", [])
        if isinstance(data, dict):
            for field in required:
                if field not in data:
                    errors.append(f"Missing required field: {field}")

        # Check type constraints
        properties = schema.get("properties", {})
        if isinstance(data, dict):
            for key, prop_schema in properties.items():
                if key in data:
                    expected_type = prop_schema.get("type")
                    if expected_type == "string" and not isinstance(data[key], str):
                        errors.append(
                            f"Field '{key}': expected string, got {type(data[key]).__name__}"
                        )
                    elif expected_type == "number" and not isinstance(data[key], (int, float)):
                        errors.append(
                            f"Field '{key}': expected number, got {type(data[key]).__name__}"
                        )
                    elif expected_type == "boolean" and not isinstance(data[key], bool):
                        errors.append(
                            f"Field '{key}': expected boolean, got {type(data[key]).__name__}"
                        )
                    elif expected_type == "array" and not isinstance(data[key], list):
                        errors.append(
                            f"Field '{key}': expected array, got {type(data[key]).__name__}"
                        )

                    # Range checks
                    if "minimum" in prop_schema and isinstance(data[key], (int, float)):
                        if data[key] < prop_schema["minimum"]:
                            errors.append(
                                f"Field '{key}': {data[key]} < minimum {prop_schema['minimum']}"
                            )
                    if "maximum" in prop_schema and isinstance(data[key], (int, float)):
                        if data[key] > prop_schema["maximum"]:
                            errors.append(
                                f"Field '{key}': {data[key]} > maximum {prop_schema['maximum']}"
                            )

        # Tripwire on too many errors
        if len(errors) >= 3:
            tripwire = True

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            tripwire_triggered=tripwire,
            sanitized_value=data,
        )

    def sanitize_text(self, text: str) -> str:
        """Remove control characters and bound length."""
        # Strip control chars (except newline, tab, carriage return)
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        # Bound length
        if len(sanitized) > self._max_length:
            sanitized = sanitized[: self._max_length] + "\n[TRUNCATED]"
        return sanitized
