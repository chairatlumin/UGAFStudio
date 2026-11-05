"""Tests for SandboxedExecutor."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from qa_framework.sandbox import (
    ExecutionResult,
    SandboxAuditEntry,
    SandboxAuditLog,
    SandboxedExecutor,
)


class TestExecutionResult:
    def test_creation(self):
        r = ExecutionResult(stdout="out", stderr="err", exit_code=0, duration_ms=100, timed_out=False)
        assert r.stdout == "out"
        assert r.exit_code == 0
        assert r.timed_out is False


class TestSandboxAuditLog:
    def _tmp_path(self, tmp_path_factory):
        return str(tmp_path_factory.mktemp("audit") / "audit.jsonl")

    def test_record_and_query(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        log = SandboxAuditLog(log_path)
        entry = SandboxAuditEntry(
            timestamp="2026-09-24T09:00:00",
            input_hash="abc123",
            output_hash="def456",
            duration_ms=500,
            exit_code=0,
            timed_out=False,
            command="echo hello",
        )
        log.record(entry)
        results = log.query()
        assert len(results) == 1
        assert results[0].input_hash == "abc123"
        assert results[0].command == "echo hello"

    def test_query_limit(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        log = SandboxAuditLog(log_path)
        for i in range(5):
            log.record(
                SandboxAuditEntry(
                    timestamp=f"2026-09-24T09:00:0{i}",
                    input_hash=f"in{i}",
                    output_hash=f"out{i}",
                    duration_ms=i,
                    exit_code=0,
                    timed_out=False,
                    command=f"cmd{i}",
                )
            )
        results = log.query(limit=3)
        assert len(results) == 3

    def test_query_since(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        log = SandboxAuditLog(log_path)
        from datetime import datetime

        log.record(
            SandboxAuditEntry(
                timestamp="2026-09-24T08:00:00",
                input_hash="old",
                output_hash="oldout",
                duration_ms=100,
                exit_code=0,
                timed_out=False,
                command="oldcmd",
            )
        )
        log.record(
            SandboxAuditEntry(
                timestamp="2026-09-24T10:00:00",
                input_hash="new",
                output_hash="newout",
                duration_ms=200,
                exit_code=0,
                timed_out=False,
                command="newcmd",
            )
        )
        cutoff = datetime(2026, 9, 24, 9, 0, 0).timestamp()
        results = log.query(since=cutoff)
        assert len(results) == 1
        assert results[0].input_hash == "new"


class TestSandboxedExecutor:
    def test_simple_command(self):
        executor = SandboxedExecutor()
        result = executor.execute(["echo", "hello"])
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.timed_out is False
        assert result.duration_ms >= 0

    def test_command_with_input(self):
        executor = SandboxedExecutor()
        result = executor.execute(["cat"], input_text="test input")
        assert "test input" in result.stdout

    def test_command_failure(self):
        executor = SandboxedExecutor()
        result = executor.execute(["false"])
        assert result.exit_code != 0

    def test_command_not_found(self):
        executor = SandboxedExecutor()
        result = executor.execute(["thiscommanddoesnotexist12345"])
        assert result.exit_code == 127
        assert "not found" in result.stderr.lower() or "not found" in result.stderr.lower()

    def test_timeout(self):
        executor = SandboxedExecutor(timeout=1)
        result = executor.execute(["sleep", "10"])
        assert result.timed_out is True
        assert result.exit_code == -1

    def test_output_limit(self, tmp_path):
        executor = SandboxedExecutor(max_output=10)
        result = executor.execute(["sh", "-c", "echo " + "x" * 1000])
        assert len(result.stdout) <= 10 + 50  # small buffer for truncation

    def test_audit_trail(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        executor = SandboxedExecutor(audit_log_path=log_path)
        result = executor.execute(["echo", "audit test"])
        assert result.exit_code == 0
        assert Path(log_path).exists()
        with open(log_path) as f:
            content = f.read()
        assert "audit test" in content or len(content) > 0

    def test_env_allowlist(self, tmp_path):
        os.environ["TEST_VAR_ALLOWLIST"] = "test_value_123"
        executor = SandboxedExecutor(env_allowlist=["TEST_VAR_ALLOWLIST", "PATH"])
        result = executor.execute(["sh", "-c", "echo $TEST_VAR_ALLOWLIST"])
        assert "test_value_123" in result.stdout

    def test_workdir(self, tmp_path):
        executor = SandboxedExecutor(workdir=str(tmp_path))
        result = executor.execute(["pwd"])
        assert "pytest-of-Admin" in result.stdout
