from __future__ import annotations

import enum
import hashlib
import json
import os
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
from typing import Any, Iterator, Optional


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


# ─────────────────────────────────────────────────────────────────────────────
# A2A TASK LIFECYCLE (Task 5–9)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TaskRecord:
    """Mirrors Google A2A Task spec."""

    task_id: str
    task_type: str = "generic"
    context_id: Optional[str] = None
    status: str = "submitted"
    history: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None

    def transition_to(self, new_status: str) -> None:
        """Transition to new status, validating with state machine."""
        if self.status == new_status:
            return  # already in this state — no-op
        sm = TaskStateMachine()
        if not sm.can_transition(self.status, new_status):
            raise ValueError(f"Invalid transition: {self.status} → {new_status}")
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_artifact(self, artifact_id: str, content: str, revision: int = 0) -> dict:
        artifact = {
            "artifact_id": artifact_id,
            "content": content,
            "revision": revision,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.artifacts.append(artifact)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return artifact

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "context_id": self.context_id,
            "status": self.status,
            "history": self.history,
            "artifacts": self.artifacts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class TaskStateMachine:
    """A2A Task lifecycle state machine."""

    def __init__(self) -> None:
        self.states = {
            "submitted",
            "working",
            "input-required",
            "completed",
            "failed",
            "canceled",
        }
        self._transitions = {
            "submitted": {"working", "canceled"},
            "working": {"completed", "failed", "input-required"},
            "input-required": {"working", "canceled"},
            "completed": set(),
            "failed": set(),
            "canceled": set(),
        }

    def can_transition(self, from_state: str, to_state: str) -> bool:
        if from_state not in self.states or to_state not in self.states:
            return False
        return to_state in self._transitions.get(from_state, set())


@dataclass
class TaskSession:
    """Checkpoints running task state to disk for crash recovery."""

    session_id: str
    checkpoint_dir: str
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        os.makedirs(self.checkpoint_dir, exist_ok=True)

    def _task_path(self, task_id: str) -> str:
        return os.path.join(self.checkpoint_dir, f"{self.session_id}_{task_id}.json")

    def save_checkpoint(self, task: TaskRecord) -> None:
        with self._lock:
            path = self._task_path(task.task_id)
            with open(path, "w") as f:
                json.dump(task.to_dict(), f, indent=2)

    def load_checkpoint(self, task_id: str) -> TaskRecord:
        path = self._task_path(task_id)
        with open(path) as f:
            data = json.load(f)
        return TaskRecord(**data)

    def list_recoverable_tasks(self) -> list[TaskRecord]:
        result = []
        with self._lock:
            for fname in os.listdir(self.checkpoint_dir):
                if fname.startswith(f"{self.session_id}_") and fname.endswith(".json"):
                    path = os.path.join(self.checkpoint_dir, fname)
                    with open(path) as f:
                        data = json.load(f)
                    t = TaskRecord(**data)
                    if t.status in ("working", "input-required"):
                        result.append(t)
        return result

    def delete_checkpoint(self, task_id: str) -> None:
        path = self._task_path(task_id)
        if os.path.exists(path):
            os.remove(path)


@dataclass
class AgentRegistry:
    """Agent Card registry — matches tasks to agents by capability."""

    _agents: dict[str, dict] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def register(self, agent_id: str, card: dict) -> None:
        with self._lock:
            self._agents[agent_id] = card

    def unregister(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)

    def can_handle(self, agent_id: str, task_type: str) -> bool:
        card = self._agents.get(agent_id, {})
        skills = card.get("skills", [])
        capabilities = card.get("capabilities", [])
        return task_type in skills or task_type in capabilities

    def best_agent(self, task_type: str) -> Optional[str]:
        candidates = []
        for agent_id, card in self._agents.items():
            skills = card.get("skills", [])
            capabilities = card.get("capabilities", [])
            if task_type in skills:
                candidates.append((agent_id, len(skills)))
            elif task_type in capabilities:
                candidates.append((agent_id, len(capabilities) + 100))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())


@dataclass
class TaskOrchestrator:
    """Orchestrate multi-agent task execution patterns."""

    def fan_out(self, tasks: list[TaskRecord], dispatch_fn: Any) -> list:
        """Dispatch tasks to parallel workers, collect results sequentially."""
        results = []
        for t in tasks:
            try:
                result = dispatch_fn(t)
                results.append(result)
            except Exception as e:
                t.transition_to("failed")
                t.error = str(e)
                results.append((t.task_id, f"error: {e}"))
        return results

    def pipeline(self, task: TaskRecord, stages: list[tuple]) -> TaskRecord:
        """Execute sequential stages. Each stage is (fn, success_status)."""
        for fn, success_status in stages:
            fn(task)
            if success_status:
                task.transition_to(success_status)
        return task


@dataclass
class ToolSelectionAdvisor:
    """Pre-dispatch classifier: should this task be dispatched to an agent?"""

    _code_keywords: list[str] = field(default_factory=lambda: [
        "write", "create", "implement", "refactor", "fix", "debug", "test",
        "parse", "generate", "build", "configure",
        "function", "class", "module", "script", "api", "endpoint",
        "sql", "query", "database",
        "docker", "kubernetes", "terraform",
    ])
    _research_keywords: list[str] = field(default_factory=lambda: [
        "summarize", "explain", "describe", "compare", "analyze",
        "review", "check", "verify", "search", "find", "look up",
        "what is", "how does", "why does", "difference between",
        "pros and cons", "advantages", "disadvantages",
    ])

    def evaluate(self, task_description: str) -> dict:
        """Evaluate task description and return dispatch recommendation."""
        desc_lower = task_description.lower()
        code_score = sum(1 for kw in self._code_keywords if kw in desc_lower)
        research_score = sum(1 for kw in self._research_keywords if kw in desc_lower)

        should_dispatch = code_score > research_score
        total = code_score + research_score
        confidence = min(0.5 + (abs(code_score - research_score) * 0.1), 0.95) if total > 0 else 0.5

        if should_dispatch:
            reasoning = (
                f"Task requires code execution ({code_score} code signals "
                f"vs {research_score} research signals)"
            )
        else:
            reasoning = (
                f"Task is research/analysis ({research_score} research signals "
                f"vs {code_score} code signals)"
            )

        return {
            "should_dispatch": should_dispatch,
            "confidence": round(confidence, 2),
            "reasoning": reasoning,
        }


@dataclass
class ParallelDispatcher:
    """Fan out multiple independent tasks using ThreadPoolExecutor."""

    max_workers: int = 4
    timeout_seconds: float = 30.0

    def dispatch(self, tasks: list) -> list[dict]:
        """Dispatch tasks in parallel, return list of {result|error} dicts in submission order."""
        import concurrent.futures

        results: list[dict] = [{"result": None, "error": "Not executed"} for _ in tasks]

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_idx = {}
            for idx, task_fn in enumerate(tasks):
                future = executor.submit(task_fn)
                future_to_idx[future] = idx

            try:
                as_completed = concurrent.futures.as_completed(
                    future_to_idx, timeout=self.timeout_seconds
                )
                for future in as_completed:
                    idx = future_to_idx[future]
                    try:
                        result = future.result(timeout=self.timeout_seconds)
                        results[idx] = {"result": result, "error": None}
                    except concurrent.futures.TimeoutError:
                        results[idx] = {"result": None, "error": "Task timed out"}
                    except Exception as e:
                        results[idx] = {"result": None, "error": str(e)}
            except concurrent.futures.TimeoutError:
                # Timeout from as_completed - remaining futures already have default error
                pass

        return results


@dataclass
class DispatchScore:
    """Score for a single dispatch event."""

    necessary: int  # 1-5: was this dispatch needed?
    complete: int   # 1-5: does the output fully address the task?
    efficient: int  # 1-5: is the output appropriately concise?

    def to_dict(self) -> dict:
        return {"necessary": self.necessary, "complete": self.complete, "efficient": self.efficient}


@dataclass
class DispatchEvaluator:
    """Post-dispatch quality scorer for agent outputs."""

    def evaluate(self, task: str, output: str) -> dict:
        """Score dispatch quality on 3 dimensions (1-5 each)."""
        output_len = len(output)
        task_len = len(task)

        has_code = bool(re.search(r'def |class |import |function|=>|{', output))
        has_action = bool(re.search(r'created|implemented|fixed|added|refactored', output.lower()))
        necessary = 5 if (has_code or has_action) else 3

        if output_len == 0:
            complete = 1
        elif output_len > task_len * 2:
            complete = 4
        else:
            complete = 3

        if output_len == 0:
            efficient = 1
        elif output_len < 200:
            efficient = 5
        elif output_len < 1000:
            efficient = 4
        elif output_len < 5000:
            efficient = 3
        elif output_len < 20000:
            efficient = 2
        else:
            efficient = 1

        score = DispatchScore(necessary=necessary, complete=complete, efficient=efficient)
        return score.to_dict()


@dataclass
class DispatchMemory:
    """Time-weighted memory of A2A dispatch outcomes for adaptive routing."""

    half_life_days: float = 7.0
    storage_path: Optional[str] = None
    _records: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        if self.storage_path and os.path.exists(self.storage_path):
            self._load()

    def record(
        self,
        agent_id: str,
        task_type: str,
        success: bool,
        score: float = 3.0,
        timestamp: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._records.append({
                "agent_id": agent_id,
                "task_type": task_type,
                "success": success,
                "score": score,
                "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            })
            if self.storage_path:
                self._save()

    def get_records(self, agent_id: str, task_type: str) -> list[dict]:
        with self._lock:
            return [
                r for r in self._records
                if r["agent_id"] == agent_id and r["task_type"] == task_type
            ]

    def recommend(self, task_type: str, candidates: list[str]) -> list[dict]:
        """Return candidates ranked by weighted success score."""
        now = datetime.now(timezone.utc)
        half_life_seconds = self.half_life_days * 86400

        results = []
        for agent_id in candidates:
            records = self.get_records(agent_id, task_type)
            if not records:
                continue

            weighted_sum = 0.0
            weight_total = 0.0
            for r in records:
                try:
                    ts = datetime.fromisoformat(r["timestamp"])
                except (ValueError, TypeError):
                    ts = now
                age_seconds = max((now - ts).total_seconds(), 0)
                if half_life_seconds > 0:
                    weight = 2 ** (-age_seconds / half_life_seconds)
                else:
                    weight = 1.0
                weighted_sum += r["score"] * weight
                weight_total += weight

            if weight_total > 0:
                results.append({
                    "agent_id": agent_id,
                    "weighted_score": round(weighted_sum / weight_total, 3),
                    "record_count": len(records),
                })

        results.sort(key=lambda x: x["weighted_score"], reverse=True)  # type: ignore[arg-type,return-value]
        return results

    def _save(self) -> None:
        if not self.storage_path:
            return
        with open(self.storage_path, "w") as f:
            json.dump(self._records, f, indent=2)

    def _load(self) -> None:
        if not self.storage_path:
            return
        try:
            with open(self.storage_path) as f:
                self._records = json.load(f)
        except (json.JSONDecodeError, IOError):
            self._records = []
