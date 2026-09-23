from __future__ import annotations

import enum
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional


class A2ATaskState(enum.Enum):
    """Google A2A Protocol task states."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class VerificationContext:
    """Self-check block embedded in every A2A brief.
    OpenCode verifies its own output against this."""

    expected_output_format: str = "markdown"  # markdown, json, yaml
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    validation_commands: list[str] = field(default_factory=list)
    schema: dict[str, str] | None = None  # expected top-level keys and types
    max_output_tokens: int | None = None

    def check_output(self, text: str) -> tuple[bool, list[str]]:
        """Return (pass, [failure_reasons])."""
        failures: list[str] = []
        for term in self.must_contain:
            if term.lower() not in text.lower():
                failures.append(f"Missing required term: {term}")
        for term in self.must_not_contain:
            if term.lower() in text.lower():
                failures.append(f"Forbidden term found: {term}")
        return (not failures, failures)


@dataclass
class ConfidenceScorer:
    """Tracks per-model/task-type success rates for adaptive routing."""

    _outcomes: dict[str, dict[str, list[bool]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list))
    )

    def record(self, model: str, task_type: str, success: bool) -> None:
        self._outcomes[model][task_type].append(success)

    def get_score(self, model: str, task_type: str) -> float:
        outcomes = self._outcomes.get(model, {}).get(task_type, [])
        if not outcomes:
            return 0.5  # unknown → neutral
        return sum(outcomes) / len(outcomes)

    def best_model(self, task_type: str, candidates: list[str]) -> str:
        """Return the model with highest score for this task type."""
        return max(candidates, key=lambda m: self.get_score(m, task_type))

    def calibration_report(self) -> dict[str, dict[str, float]]:
        """Return {model: {task_type: score}}."""
        return {
            model: {
                tt: sum(v) / len(v) for tt, v in tts.items() if v
            }
            for model, tts in self._outcomes.items()
        }


@dataclass
class SelfVerifyingOutput:
    """Structured output that OpenCode must emit at end of every task."""

    confidence: float = 0.5  # 0.0-1.0, agent's self-assessed correctness
    issues: list[str] = field(default_factory=list)
    checklist: dict[str, bool] = field(default_factory=dict)
    raw: str = ""

    @classmethod
    def parse(cls, text: str) -> SelfVerifyingOutput:
        """Parse the ## Self-Verifying Output section from OpenCode's response."""
        confidence = 0.5
        issues: list[str] = []
        checklist: dict[str, bool] = {}

        lines = text.splitlines()
        for line in lines:
            lower = line.lower()
            if "confidence" in lower and ":" in line:
                try:
                    confidence = float(line.split(":")[-1].strip())
                    confidence = max(0.0, min(1.0, confidence))
                except (ValueError, IndexError):
                    pass
            if "- " in lower and ("issue" in lower or "problem" in lower or "blocker" in lower):
                item = line[line.index("- ") + 2:].strip()
                if item and item.lower() not in ("none", "n/a", "-"):
                    issues.append(item)
        return cls(confidence=confidence, issues=issues, checklist=checklist, raw=text)

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        return self.confidence >= threshold

    def has_blockers(self) -> bool:
        return len(self.issues) > 0


@dataclass
class ConsensusDispatcher:
    """Dispatches same brief to N models, merges outputs via voting."""

    opencode_url: str = "http://127.0.0.1:4096"
    models: list[str] = field(default_factory=lambda: ["opencode/nemotron-3.5-lightning-free"])
    timeout: int = 300

    def _build_brief(
        self,
        goal: str,
        context: str,
        validation_cmds: list[str],
        vc: VerificationContext | None = None,
    ) -> str:
        lines = [
            "# Task",
            goal,
            "",
            "## Context",
            context or "(none)",
            "",
            "## Constraints",
            "- Use the Self-Verifying Output format at the end",
            "- Be concise and direct",
        ]
        if validation_cmds:
            lines.extend(["", "## Validation", "Run these yourself:"])
            for cmd in validation_cmds:
                lines.append(f"  {cmd}")
        lines.extend([
            "",
            "## Self-Verifying Output",
            "End your response with this exact format:",
            "```",
            "## Confidence: <0.0-1.0>",
            "## Issues:",
            "- <list any issues, or 'none'>",
            "## Self-Check:",
            "- format ok",
            "- goal met",
            "```",
        ])
        if vc:
            if vc.must_contain:
                lines.extend(["", "## Must Contain", ", ".join(vc.must_contain)])
            if vc.must_not_contain:
                lines.extend(["", "## Must NOT Contain", ", ".join(vc.must_not_contain)])
        return "\n".join(lines)

    def dispatch(
        self,
        goal: str,
        context: str = "",
        validation_cmds: list[str] | None = None,
        vc: VerificationContext | None = None,
    ) -> list[A2ATask]:
        """Dispatch to all models in parallel, return task handles."""
        validation_cmds = validation_cmds or []
        brief = self._build_brief(goal, context, validation_cmds, vc)
        tasks: list[A2ATask] = []
        for model in self.models:
            adapter = A2AAdapter(opencode_url=self.opencode_url, default_model=model)
            task = adapter.submit_task(prompt=brief, agent="opencode")
            tasks.append(task)
        return tasks

    def merge_results(
        self,
        tasks: list[A2ATask],
        agreement_threshold: float = 0.6,
    ) -> tuple[str, float]:
        """Merge completed task outputs. Returns (best_output, confidence)."""
        completed = [t for t in tasks if t.state == A2ATaskState.COMPLETED and t.output]
        if not completed:
            return ("", 0.0)
        if len(completed) == 1:
            return (completed[0].output or "", 0.5)
        # Simple agreement: shared lines / max lines
        outputs = [set((t.output or "").splitlines()) for t in completed]
        common: set[str] = set.intersection(*outputs) if outputs else set()
        max_lines = max(len(o) for o in outputs) if outputs else 1
        agreement = len(common) / max(max_lines, 1)
        # Pick longest output as representative (usually the most complete)
        best = max(completed, key=lambda t: len(t.output or ""))
        confidence = min(agreement + 0.3, 1.0)
        return (best.output or "", confidence)


@dataclass
class AdaptiveModelRouter:
    """Routes tasks to models based on historical confidence."""

    scorer: ConfidenceScorer
    fallback_model: str = "opencode/nemotron-3.5-lightning-free"

    def select_model(self, task_type: str, candidates: list[str]) -> str:
        """Select the best model for this task type."""
        if not candidates:
            return self.fallback_model
        try:
            return self.scorer.best_model(task_type, candidates)
        except Exception:
            return self.fallback_model

    def classify_task_type(self, brief: str) -> str:
        """Heuristic classification of task type from brief content."""
        brief_lower = brief.lower()
        if "test" in brief_lower and ("qa" in brief_lower or "quality" in brief_lower):
            return "qa_runner"
        if "review" in brief_lower or "code review" in brief_lower:
            return "code_review"
        if "fix" in brief_lower or "bug" in brief_lower or "error" in brief_lower:
            return "bug_fix"
        if "document" in brief_lower or "doc" in brief_lower:
            return "documentation"
        if "refactor" in brief_lower:
            return "refactoring"
        return "code_generation"


@dataclass
class A2ATask:
    """A2A Protocol task with lifecycle."""

    id: str
    prompt: str
    agent: str
    state: A2ATaskState = A2ATaskState.SUBMITTED
    output: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def mark_working(self) -> None:
        with self._lock:
            self.state = A2ATaskState.WORKING
            self.updated_at = time.monotonic()

    def mark_completed(self, output: str) -> None:
        with self._lock:
            self.state = A2ATaskState.COMPLETED
            self.output = output
            self.updated_at = time.monotonic()

    def mark_failed(self, error: str) -> None:
        with self._lock:
            self.state = A2ATaskState.FAILED
            self.error = error
            self.updated_at = time.monotonic()


@dataclass
class A2AAdapter:
    """Adapter for Google A2A Protocol task-based communication."""

    opencode_url: str = "http://127.0.0.1:4096"
    default_model: str = "opencode/nemotron-3.5-lightning-free"
    _tasks: dict[str, A2ATask] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def submit_task(
        self,
        prompt: str,
        agent: str = "opencode",
        title: str = "A2A Protocol Task",
    ) -> A2ATask:
        task_id = f"a2a-{uuid.uuid4().hex[:12]}"
        task = A2ATask(id=task_id, prompt=prompt, agent=agent)
        with self._lock:
            self._tasks[task_id] = task
        # Fire-and-poll: dispatch async, return task handle
        threading.Thread(
            target=self._dispatch,
            args=(task,),
            daemon=True,
        ).start()
        return task

    def _dispatch(self, task: A2ATask) -> None:
        try:
            task.mark_working()
            # Create session
            req = urllib.request.Request(
                f"{self.opencode_url}/session",
                data=json.dumps({"title": task.id}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                session_data = json.loads(resp.read().decode())
                session_id = session_data.get("id")
            if not session_id:
                task.mark_failed("No session ID returned")
                return
            # Send prompt async
            prompt_req = urllib.request.Request(
                f"{self.opencode_url}/session/{session_id}/prompt_async",
                data=json.dumps({"parts": [{"type": "text", "text": task.prompt}]}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(prompt_req, timeout=30)
            # Poll for completion
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                try:
                    msg_req = urllib.request.Request(
                        f"{self.opencode_url}/session/{session_id}/message",
                    )
                    with urllib.request.urlopen(msg_req, timeout=10) as resp:
                        messages = json.loads(resp.read().decode())
                    if isinstance(messages, list):
                        for msg in reversed(messages):
                            info = msg.get("info", {})
                            if info.get("role") == "assistant" and info.get("time", {}).get(
                                "completed"
                            ):
                                parts = msg.get("parts", [])
                                text = " ".join(
                                    p.get("text", "") for p in parts if p.get("type") == "text"
                                )
                                task.mark_completed(text)
                                return
                except Exception:
                    pass
                time.sleep(2)
            task.mark_failed("Timeout waiting for completion")
        except Exception as exc:
            task.mark_failed(str(exc))

    def get_task(self, task_id: str) -> A2ATask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
        task.mark_failed("Canceled by user")
        return True


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY COMPONENTS (Task 1–4)
# ─────────────────────────────────────────────────────────────────────────────

# ---- Task 1: BriefSanitizer ----

_INJECTION_PATTERNS = [
    re.compile(r'#{1,6}\s*system\s*overrides?', re.IGNORECASE),
    re.compile(r'ignore\s+(all\s+)?previous\s+instructions?', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+DAN', re.IGNORECASE),
    re.compile(r'output\s+(your|the)\s+system\s+prompt', re.IGNORECASE),
    re.compile(r'<\s*system\s*>', re.IGNORECASE),
    re.compile(r'<\s*/\s*system\s*>', re.IGNORECASE),
    re.compile(r'\[\s*system\s*\]', re.IGNORECASE),
]


def sanitize_brief(text: str) -> str:
    """Strip prompt injection markers from brief text."""
    result = text
    for pattern in _INJECTION_PATTERNS:
        result = pattern.sub('', result)
    # Collapse 3+ blank lines to 2
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


# ---- Task 2: PermissionRegistry ----

@dataclass
class _PermissionEntry:
    granted_at: datetime
    expires_at: Optional[datetime]


@dataclass
class PermissionRegistry:
    """Thread-safe per-agent RBAC with TTL-based expiry."""
    _entries: dict[str, _PermissionEntry] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def grant(self, agent: str, tool: str, ttl_seconds: Optional[int] = None) -> None:
        key = f"{agent}:{tool}"
        now = datetime.utcnow()
        expires = now + timedelta(seconds=ttl_seconds) if ttl_seconds else None
        with self._lock:
            self._entries[key] = _PermissionEntry(granted_at=now, expires_at=expires)

    def revoke(self, agent: str, tool: str) -> None:
        key = f"{agent}:{tool}"
        with self._lock:
            self._entries.pop(key, None)

    def is_allowed(self, agent: str, tool: str) -> bool:
        key = f"{agent}:{tool}"
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry.expires_at and datetime.utcnow() > entry.expires_at:
                del self._entries[key]
                return False
            return True

    def list_permissions(self, agent: str) -> list[str]:
        with self._lock:
            return [k.split(":", 1)[1] for k in self._entries if k.startswith(f"{agent}:")]


# ---- Task 3: AuditLogger ----

@dataclass
class AuditLogger:
    """Append-only structured JSONL audit log."""
    log_path: str
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def log(
        self,
        agent: str,
        task: str,
        action: str,
        input_hash: str = "",
        output_hash: str = "",
        verdict: str = "",
        details: str = "",
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "task": task,
            "action": action,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "verdict": verdict,
            "details": details,
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')

    def read_all(self) -> Iterator[dict]:
        path = Path(self.log_path)
        if not path.exists():
            return
        with path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    @staticmethod
    def hash_content(text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


# ---- Task 4: OutputValidator ----

@dataclass
class OutputValidator:
    """Scan agent outputs for secrets, injection markers, safety violations."""
    _secret_patterns: list[re.Pattern] = field(
        default_factory=lambda: [
            re.compile(
                r'(?:api_key|apikey|secret|token|password|passwd)\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{16,}',
                re.IGNORECASE,
            ),
            re.compile(r'sk-[a-zA-Z0-9]{20,}', re.IGNORECASE),
            re.compile(r'AKIA[0-9A-Z]{16}', re.IGNORECASE),
            re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', re.IGNORECASE),
        ]
    )
    _injection_patterns: list[re.Pattern] = field(
        default_factory=lambda: [
            re.compile(r'ignore\s+(all\s+)?previous\s+instructions?', re.IGNORECASE),
            re.compile(r'you\s+are\s+now\s+DAN', re.IGNORECASE),
            re.compile(r'delete\s+(all\s+)?files', re.IGNORECASE),
            re.compile(r'rm\s+-rf\s+/', re.IGNORECASE),
        ]
    )

    def scan(self, text: str) -> list[str]:
        issues: list[str] = []
        for pat in self._secret_patterns:
            if pat.search(text):
                issues.append(f"Secret pattern detected: {pat.pattern[:50]}...")
        for pat in self._injection_patterns:
            if pat.search(text):
                issues.append(f"Injection pattern detected: {pat.pattern[:50]}...")
        return issues

    def is_safe(self, text: str) -> bool:
        return len(self.scan(text)) == 0
