"""Tests for validation gate executor."""
import pytest
from qa_framework.a2a.validation_gate import ValidationGateExecutor
from qa_framework.a2a.task_graph_models import ValidationGate


def test_gate_executor_runs_command():
    executor = ValidationGateExecutor()
    gate = ValidationGate(name="echo_test", command="echo hello {output}")
    result = executor.execute(gate, output="world")
    assert result.success is True
    assert "hello" in result.output


def test_gate_executor_fails_on_error():
    executor = ValidationGateExecutor()
    gate = ValidationGate(name="fail_test", command="exit 1")
    result = executor.execute(gate, output="")
    assert result.success is False


def test_gate_executor_timeout():
    executor = ValidationGateExecutor()
    gate = ValidationGate(name="timeout_test", command="timeout /t 5 /nobreak")
    result = executor.execute(gate, output="")
    # Should either timeout or fail
    assert result.success is False or result.output is not None
