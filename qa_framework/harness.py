"""Harness layer for A2A agent dispatch — routing, permissions, retry, tracing."""

from __future__ import annotations

import enum
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# ─── Deterministic Router ────────────────────────────────────────────────────

@dataclass(frozen=True)
class AgentConfig:
    """Resolved agent configuration from the router."""
    agent_id: str
    model: str
    working_dir: str
    tools: frozenset[str]
    max_runtime: int  # seconds
    env_vars: dict[str, str] = field(default_factory=dict)


# Rule table: (game_id, task_type) → AgentConfig
_ROUTE_TABLE: dict[tuple[str, str], AgentConfig] = {
    ("4077460", "smoke"): AgentConfig(
        agent_id="shinebringer-qa",
        model="opencode/nemotron-3.5-lightning-free",
        working_dir="C:/Users/Admin/UGAFStudio",
        tools=frozenset({"pytest", "python", "git"}),
        max_runtime=300,
    ),
    ("4077460", "gameplay"): AgentConfig(
        agent_id="shinebringer-gameplay",
        model="opencode/nemotron-3.5-lightning-free",
        working_dir="C:/Users/Admin/UGAFStudio",
        tools=frozenset({"pytest", "python", "git", "opencv", "mss"}),
        max_runtime=600,
    ),
    ("4307180", "smoke"): AgentConfig(
        agent_id="agentveil-qa",
        model="opencode/nemotron-3.5-lightning-free",
        working_dir="C:/Users/Admin/UGAFStudio",
        tools=frozenset({"pytest", "python", "git"}),
        max_runtime=300,
    ),
    ("4511140", "smoke"): AgentConfig(
        agent_id="love-qa",
        model="opencode/nemotron-3.5-lightning-free",
        working_dir="C:/Users/Admin/UGAFStudio",
        tools=frozenset({"pytest", "python", "git"}),
        max_runtime=300,
    ),
}


class Router:
    """Deterministic router: maps (game_id, task_type) → AgentConfig."""

    def __init__(self, route_table: dict[tuple[str, str], AgentConfig] | None = None) -> None:
        self._table = route_table or _ROUTE_TABLE

    def route(self, game_id: str, task_type: str) -> AgentConfig | None:
        """Look up agent config. Returns None if no rule matches (escalate)."""
        return self._table.get((game_id, task_type))


# ─── Permission Checker ──────────────────────────────────────────────────────

# Deny-by-default: these commands are never allowed
_DENY_PATTERNS: frozenset[str] = frozenset({
    "rm -rf",
    "rm -fr",
    "git push --force",
    "git push -f",
    "del /f",
    "format ",
    "shutdown",
    "reboot",
    "reg delete",
})


class PermissionChecker:
    """Checks if a command is allowed for a given agent config."""

    def __init__(self, agent_config: AgentConfig) -> None:
        self._config = agent_config

    def is_allowed(self, command: str) -> tuple[bool, str]:
        """Check command against deny patterns and tool whitelist.

        Returns (allowed: bool, reason: str).
        """
        cmd_lower = command.lower().strip()

        # Check deny patterns
        for pattern in _DENY_PATTERNS:
            if pattern in cmd_lower:
                return False, f"Blocked by deny pattern: {pattern}"

        # Check tool whitelist — command must start with an allowed tool
        first_word = cmd_lower.split()[0] if cmd_lower else ""
        # Strip path prefix (e.g., /usr/bin/git → git)
        tool_name = os.path.basename(first_word)

        if tool_name not in self._config.tools:
            return False, f"Tool '{tool_name}' not in whitelist: {sorted(self._config.tools)}"

        return True, "OK"


# ─── Dispatch Result ─────────────────────────────────────────────────────────

class DispatchStatus(enum.Enum):
    SUCCESS = "success"
    RETRY = "retry"
    ESCALATE = "escalate"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


@dataclass
class DispatchResult:
    """Result of a dispatch attempt."""
    status: DispatchStatus
    agent_id: str
    game_id: str
    task_type: str
    elapsed: float
    attempts: int
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    reason: str = ""

    @property
    def success(self) -> bool:
        return self.status == DispatchStatus.SUCCESS

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "agent_id": self.agent_id,
            "game_id": self.game_id,
            "task_type": self.task_type,
            "elapsed": round(self.elapsed, 3),
            "attempts": self.attempts,
            "exit_code": self.exit_code,
            "reason": self.reason,
        }


# ─── Trace Logger ────────────────────────────────────────────────────────────

@dataclass
class TraceLogger:
    """Persists dispatch traces to disk."""
    log_dir: str = "C:/Users/Admin/.ai/a2a/traces"
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

    def log(self, result: DispatchResult) -> str:
        """Write a trace entry. Returns the path written."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = os.path.join(self.log_dir, f"trace-{now}-{result.agent_id}.json")

        import json
        entry = {
            "timestamp": now,
            **result.to_dict(),
            "stdout_preview": result.stdout[:200] if result.stdout else "",
            "stderr_preview": result.stderr[:200] if result.stderr else "",
        }

        with self._lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entry, f, indent=2)

        return path


# ─── Dispatch Wrapper ────────────────────────────────────────────────────────

@dataclass
class DispatchWrapper:
    """Wraps subprocess dispatch with retry, permission check, and tracing."""
    router: Router = field(default_factory=Router)
    trace_logger: TraceLogger = field(default_factory=TraceLogger)
    max_retries: int = 3
    base_delay: float = 2.0  # exponential backoff base (seconds)

    def dispatch(
        self,
        game_id: str,
        task_type: str,
        command: str,
        *,
        timeout: int | None = None,
    ) -> DispatchResult:
        """Dispatch a command to the appropriate agent.

        1. Route (deterministic lookup)
        2. Permission check
        3. Execute with retry + exponential backoff
        4. Log trace
        """
        start = time.monotonic()

        # 1. Route
        config = self.router.route(game_id, task_type)
        if config is None:
            elapsed = time.monotonic() - start
            result = DispatchResult(
                status=DispatchStatus.ESCALATE,
                agent_id="unknown",
                game_id=game_id,
                task_type=task_type,
                elapsed=elapsed,
                attempts=0,
                reason=f"No route for ({game_id}, {task_type})",
            )
            self.trace_logger.log(result)
            return result

        # 2. Permission check
        checker = PermissionChecker(config)
        allowed, reason = checker.is_allowed(command)
        if not allowed:
            elapsed = time.monotonic() - start
            result = DispatchResult(
                status=DispatchStatus.BLOCKED,
                agent_id=config.agent_id,
                game_id=game_id,
                task_type=task_type,
                elapsed=elapsed,
                attempts=0,
                reason=reason,
            )
            self.trace_logger.log(result)
            return result

        # 3. Execute with retry
        effective_timeout = timeout or config.max_runtime
        last_exit_code: int | None = None
        last_stdout = ""
        last_stderr = ""

        for attempt in range(1, self.max_retries + 1):
            try:
                proc = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    cwd=config.working_dir,
                    env={**os.environ, **config.env_vars},
                )
                last_exit_code = proc.returncode
                last_stdout = proc.stdout
                last_stderr = proc.stderr

                if proc.returncode == 0:
                    elapsed = time.monotonic() - start
                    result = DispatchResult(
                        status=DispatchStatus.SUCCESS,
                        agent_id=config.agent_id,
                        game_id=game_id,
                        task_type=task_type,
                        elapsed=elapsed,
                        attempts=attempt,
                        stdout=last_stdout,
                        stderr=last_stderr,
                        exit_code=0,
                    )
                    self.trace_logger.log(result)
                    return result

                # Non-zero exit — retry unless last attempt
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    time.sleep(delay)

            except subprocess.TimeoutExpired:
                last_exit_code = -1
                last_stderr = f"Command timed out after {effective_timeout}s"
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    time.sleep(delay)

            except Exception as e:
                last_exit_code = -2
                last_stderr = str(e)
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    time.sleep(delay)

        # All retries exhausted
        elapsed = time.monotonic() - start
        status = (
            DispatchStatus.TIMEOUT if last_exit_code == -1
            else DispatchStatus.ESCALATE
        )
        result = DispatchResult(
            status=status,
            agent_id=config.agent_id,
            game_id=game_id,
            task_type=task_type,
            elapsed=elapsed,
            attempts=self.max_retries,
            stdout=last_stdout,
            stderr=last_stderr,
            exit_code=last_exit_code,
            reason=f"All {self.max_retries} attempts failed",
        )
        self.trace_logger.log(result)
        return result


# ─── Trace Aggregator ──────────────────────────────────────────────────────

@dataclass
class TraceAggregator:
    """Aggregate dispatch traces for cross-agent analytics."""
    log_dir: str = "C:/Users/Admin/.ai/a2a/traces"

    def aggregate(self) -> dict:
        """Read all trace files and produce summary stats."""
        traces = self._load_traces()
        if not traces:
            return {"total_traces": 0, "agents": {}, "overall": {}}

        agents: dict[str, dict] = {}
        for t in traces:
            agent_id = t.get("agent_id", "unknown")
            if agent_id not in agents:
                agents[agent_id] = {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "blocked": 0,
                    "total_elapsed": 0.0,
                }
            agents[agent_id]["total"] += 1
            agents[agent_id]["total_elapsed"] += t.get("elapsed", 0.0)
            status = t.get("status", "")
            if status == "success":
                agents[agent_id]["success"] += 1
            elif status == "blocked":
                agents[agent_id]["blocked"] += 1
            else:
                agents[agent_id]["failed"] += 1

        total = sum(a["total"] for a in agents.values())
        total_success = sum(a["success"] for a in agents.values())
        return {
            "total_traces": total,
            "agents": agents,
            "overall": {
                "success_rate": round(total_success / total, 4) if total else 0.0,
                "total_elapsed": round(sum(a["total_elapsed"] for a in agents.values()), 3),
            },
        }

    def _load_traces(self) -> list[dict]:
        """Load all JSON trace files from log_dir."""
        import json
        from pathlib import Path

        log_path = Path(self.log_dir)
        if not log_path.exists():
            return []
        traces: list[dict] = []
        for f in log_path.glob("trace-*.json"):
            try:
                traces.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
        return traces
