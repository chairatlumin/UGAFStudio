import re
from typing import Any

FORBIDDEN_PATTERNS = [
    r'^(?:rm|del|format|shutdown|reboot)\b',
    r';\s*(?:rm|curl|wget|sh|bash|python|eval|exec|powershell)\b',
    r'\|\s*(?:rm|curl|wget|sh|bash|python|eval|exec|powershell)\b',
    r'`[^`]+`',
    r'--?api[-_]?key',
    r'sk-[a-zA-Z0-9]{20,}',
    r'AKIA[0-9A-Z]{16}',
    r'password\s*[:=]\s*\S+',
    r'token\s*[:=]\s*\S+',
    r'secret\s*[:=]\s*\S+',
]

FORBIDDEN_RE = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PATTERNS]


def validate_a2a_message(msg: dict[str, Any]) -> None:
    """Validate A2A message schema and content. Raises ValueError on violation."""
    if not isinstance(msg, dict):
        raise ValueError("schema: message must be a dict")
    if "command" not in msg:
        raise ValueError("schema: missing 'command' field")
    if not isinstance(msg["command"], str):
        raise ValueError("schema: 'command' must be a string")

    command = msg["command"]

    for pattern in FORBIDDEN_RE:
        match = pattern.search(command)
        if match:
            raise ValueError(
                f"forbidden pattern: '{match.group()}' in command"
            )


def sanitize_command(command: str) -> str:
    """Return sanitized command or empty string if dangerous."""
    if not command:
        return ""

    for pattern in FORBIDDEN_RE:
        if pattern.search(command):
            return ""

    return command


def is_safe_for_execution(command: str) -> bool:
    """Quick check if command is safe to execute."""
    try:
        validate_a2a_message({"command": command, "agent_id": "check"})
        return True
    except ValueError:
        return False
