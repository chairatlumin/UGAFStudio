from __future__ import annotations

import json

import pytest

from qa_framework.a2a_spec_compliance import AgentCard, TaskLifecycle


class TestAgentCard:
    def test_creation(self):
        card = AgentCard(
            name="UGAFStudio Agent",
            description="Game QA orchestration",
            version="1.0.0",
        )
        assert card.name == "UGAFStudio Agent"
        assert card.url == "http://localhost:4096"

    def test_to_dict(self):
        card = AgentCard(
            name="Test Agent",
            description="Test",
            version="2.0.0",
            capabilities=["dispatch", "verify"],
            authentication={"type": "none"},
        )
        d = card.to_dict()
        assert d["name"] == "Test Agent"
        assert d["version"] == "2.0.0"
        assert "dispatch" in d["capabilities"]
        assert d["authentication"]["type"] == "none"

    def test_to_json(self):
        card = AgentCard(name="Test", description="Test agent", version="1.0.0")
        j = card.to_json()
        parsed = json.loads(j)
        assert parsed["name"] == "Test"

    def test_validate_valid(self):
        card = AgentCard(
            name="Test",
            description="Test agent",
            version="1.0.0",
            capabilities=["run_tests"],
            authentication={"type": "none"},
        )
        errors = card.validate()
        assert len(errors) == 0

    def test_validate_missing_name(self):
        card = AgentCard(name="", description="Test", version="1.0.0", capabilities=["run"])
        errors = card.validate()
        assert any("name" in e for e in errors)

    def test_validate_missing_version(self):
        card = AgentCard(name="Test", description="Test", version="", capabilities=["run"])
        errors = card.validate()
        assert any("version" in e for e in errors)

    def test_validate_missing_capabilities(self):
        card = AgentCard(name="Test", description="Test", version="1.0.0", capabilities=[])
        errors = card.validate()
        assert any("capability" in e for e in errors)

    def test_validate_invalid_auth_type(self):
        card = AgentCard(
            name="Test",
            description="Test",
            version="1.0.0",
            capabilities=["run"],
            authentication={"type": "invalid"},
        )
        errors = card.validate()
        assert any("auth" in e for e in errors)

    def test_validate_valid_oauth2(self):
        card = AgentCard(
            name="Test",
            description="Test",
            version="1.0.0",
            capabilities=["run"],
            authentication={"type": "oauth2"},
        )
        errors = card.validate()
        assert len(errors) == 0

    def test_provider_optional(self):
        card = AgentCard(
            name="Test",
            description="Test",
            version="1.0.0",
            capabilities=["run"],
            provider={"name": "Nous Research", "url": "https://nousresearch.com"},
        )
        d = card.to_dict()
        assert d["provider"]["name"] == "Nous Research"

    def test_skills_optional(self):
        card = AgentCard(
            name="Test",
            description="Test",
            version="1.0.0",
            capabilities=["run"],
            skills=[{"name": "dispatch", "description": "Dispatch tasks"}],
        )
        d = card.to_dict()
        assert len(d["skills"]) == 1


class TestTaskLifecycle:
    def test_creation(self):
        tl = TaskLifecycle(task_id="task-123")
        assert tl.task_id == "task-123"
        assert tl.state == "submitted"

    def test_valid_transition(self):
        tl = TaskLifecycle(task_id="t1")
        tl.transition("working")
        assert tl.state == "working"
        tl.transition("completed")
        assert tl.state == "completed"

    def test_invalid_transition(self):
        tl = TaskLifecycle(task_id="t1")
        with pytest.raises(ValueError, match="Invalid transition"):
            tl.transition("completed")

    def test_cancel_from_submitted(self):
        tl = TaskLifecycle(task_id="t1")
        tl.transition("canceled")
        assert tl.state == "canceled"

    def test_cancel_from_working(self):
        tl = TaskLifecycle(task_id="t1")
        tl.transition("working")
        tl.transition("canceled")
        assert tl.state == "canceled"

    def test_input_required_transition(self):
        tl = TaskLifecycle(task_id="t1")
        tl.transition("working")
        tl.transition("input-required")
        assert tl.state == "input-required"
        tl.transition("working")
        assert tl.state == "working"

    def test_add_message(self):
        tl = TaskLifecycle(task_id="t1")
        tl.add_message("user", "run tests", metadata={"source": "cli"})
        assert len(tl.history) == 1
        assert tl.history[0]["role"] == "user"
        assert tl.history[0]["parts"][0]["text"] == "run tests"

    def test_add_artifact(self):
        tl = TaskLifecycle(task_id="t1")
        tl.add_artifact("log", "test output", metadata={"type": "stdout"})
        assert len(tl.artifacts) == 1
        assert tl.artifacts[0]["artifact_type"] == "log"
        assert tl.artifacts[0]["content"] == "test output"

    def test_to_dict(self):
        tl = TaskLifecycle(task_id="t1")
        tl.add_message("user", "test")
        d = tl.to_dict()
        assert d["task_id"] == "t1"
        assert d["state"] == "submitted"
        assert len(d["history"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
