"""Regression test for the qa_framework.gameplay_agent public API surface."""

from __future__ import annotations

from qa_framework.gameplay_agent import (
    Action,
    ActionExecutor,
    EchoVLMBackend,
    FrameDiffReward,
    GameplayAgent,
    MOAAgent,
    OpenAICompatBackend,
    RandomAgent,
    VLMAgent,
    VLMBackend,
)


def test_public_api_imports_resolve() -> None:
    """All documented public symbols are importable from the package root."""
    assert GameplayAgent.__name__ == "GameplayAgent"
    assert Action.__name__ == "Action"
    assert ActionExecutor.__name__ == "ActionExecutor"
    assert FrameDiffReward.__name__ == "FrameDiffReward"
    assert RandomAgent.__name__ == "RandomAgent"
    assert VLMBackend.__name__ == "VLMBackend"
    assert EchoVLMBackend.__name__ == "EchoVLMBackend"
    assert OpenAICompatBackend.__name__ == "OpenAICompatBackend"
    assert VLMAgent.__name__ == "VLMAgent"
    assert MOAAgent.__name__ == "MOAAgent"
