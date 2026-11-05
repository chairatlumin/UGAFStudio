"""Sandboxed subprocess executor with audit trail for UGAFStudio."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Optional

__all__ = [
    "ExecutionResult",
    "SandboxAuditEntry",
    "SandboxAuditLog",
    "SandboxedExecutor",
]


class ExecutionResult(NamedTuple):
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool


class SandboxAuditEntry(NamedTuple):
    timestamp: str
    input_hash: str
    output_hash: str
    duration_ms: int
    exit_code: int
    timed_out: bool
    command: str


class SandboxAuditLog:
    """Append-only audit log for sandboxed executions."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: SandboxAuditEntry) -> None:
        data = {
            "timestamp": entry.timestamp,
            "input_hash": entry.input_hash,
            "output_hash": entry.output_hash,
            "duration_ms": entry.duration_ms,
            "exit_code": entry.exit_code,
            "timed_out": entry.timed_out,
            "command": entry.command,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")

    def query(
        self, since: Optional[float] = None, limit: int = 100
    ) -> list[SandboxAuditEntry]:
        entries: list[SandboxAuditEntry] = []
        if not self.path.exists():
            return entries
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if since is not None:
                    ts = datetime.fromisoformat(data["timestamp"]).timestamp()
                    if ts < since:
                        continue
                entries.append(SandboxAuditEntry(**data))
        return entries[-limit:]


class SandboxedExecutor:
    """Execute commands with timeout, output limits, and audit trail."""

    def __init__(
        self,
        timeout: int = 600,
        max_output: int = 50000,
        env_allowlist: Optional[list[str]] = None,
        workdir: Optional[str] = None,
        audit_log_path: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self.max_output = max_output
        self.env_allowlist = env_allowlist
        self.workdir = workdir
        self.audit_log: Optional[SandboxAuditLog] = (
            SandboxAuditLog(audit_log_path) if audit_log_path else None
        )

    def execute(
        self, cmd: list[str], input_text: Optional[str] = None
    ) -> ExecutionResult:
        start = time.monotonic()
        inp = (input_text or "").encode("utf-8")
        input_hash = hashlib.sha256(inp).hexdigest()[:16]

        env: Optional[dict[str, str]] = None
        if self.env_allowlist is not None:
            env = {
                k: os.environ[k]
                for k in self.env_allowlist
                if k in os.environ
            }
            env["PATH"] = os.environ.get("PATH", "")

        kwargs: dict = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.PIPE if input_text is not None else None,
            "cwd": self.workdir,
            "env": env,
        }

        try:
            proc = subprocess.Popen(cmd, **kwargs)
            try:
                stdout_b, stderr_b = proc.communicate(inp, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_b, stderr_b = proc.communicate()
                duration_ms = int((time.monotonic() - start) * 1000)
                result = ExecutionResult(
                    stdout=stdout_b.decode("utf-8", errors="replace")[: self.max_output],
                    stderr=stderr_b.decode("utf-8", errors="replace")[: self.max_output],
                    exit_code=-1,
                    duration_ms=duration_ms,
                    timed_out=True,
                )
                if self.audit_log is not None:
                    self.audit_log.record(
                        SandboxAuditEntry(
                            timestamp=datetime.now().isoformat(),
                            input_hash=input_hash,
                            output_hash=hashlib.sha256(stdout_b).hexdigest()[:16],
                            duration_ms=duration_ms,
                            exit_code=-1,
                            timed_out=True,
                            command=" ".join(cmd),
                        )
                    )
                return result

            duration_ms = int((time.monotonic() - start) * 1000)
            stdout_s = stdout_b.decode("utf-8", errors="replace")[: self.max_output]
            stderr_s = stderr_b.decode("utf-8", errors="replace")[: self.max_output]
            result = ExecutionResult(
                stdout=stdout_s,
                stderr=stderr_s,
                exit_code=proc.returncode,
                duration_ms=duration_ms,
                timed_out=False,
            )
            if self.audit_log is not None:
                self.audit_log.record(
                    SandboxAuditEntry(
                        timestamp=datetime.now().isoformat(),
                        input_hash=input_hash,
                        output_hash=hashlib.sha256(stdout_b).hexdigest()[:16],
                        duration_ms=duration_ms,
                        exit_code=proc.returncode,
                        timed_out=False,
                        command=" ".join(cmd),
                    )
                )
            return result
        except FileNotFoundError:
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecutionResult(
                stdout="",
                stderr=f"Command not found: {cmd[0]}",
                exit_code=127,
                duration_ms=duration_ms,
                timed_out=False,
            )
