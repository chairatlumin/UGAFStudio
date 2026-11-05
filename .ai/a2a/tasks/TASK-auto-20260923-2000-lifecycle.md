# TASK: A2A Task Lifecycle & Persistent Agent State

## Goal
Add 5 new dataclasses to `qa_framework/a2a_adapter.py` so long-running QA tasks survive interruptions and dispatch to matched agents — Google A2A-spec Task lifecycle, checkpoint/recovery, Agent Card registry, and Task orchestrator.

## Context

**Existing codebase (DO NOT break):**
- `C:/Users/Admin/UGAFStudio/qa_framework/a2a_adapter.py` (~400 lines, already has VerificationContext, ConfidenceScorer, SelfVerifyingOutput, ConsensusDispatcher, AdaptiveModelRouter, sanitize_brief, PermissionRegistry, AuditLogger, OutputValidator)
- `C:/Users/Admin/UGAFStudio/qa_framework/tests/test_a2a_adapter.py` (34 tests, all passing)

**Requirements:** Add 5 new components:
1. `TaskRecord` — dataclass mirroring Google A2A Task spec: `task_id`, `task_type`, `context_id`, `status` (submitted/working/input-required/completed/failed/canceled), `history`, `artifacts`, `created_at`, `updated_at`, `error`. Methods: `transition_to()`, `add_artifact()`, `to_dict()`, `to_json()`.
2. `TaskStateMachine` — explicit A2A state transitions. `states` set, `_transitions` dict, `can_transition(from, to) → bool`. Terminal states: completed, failed, canceled.
3. `TaskSession` — serializes running task state to disk (JSON), auto-checkpoint every 30s, auto-recovery on restart. Fields: `session_id`, `checkpoint_dir`, `_lock`. Methods: `save_checkpoint(task)`, `load_checkpoint(task_id) → TaskRecord`, `list_recoverable_tasks() → list[TaskRecord]`, `delete_checkpoint(task_id)`.
4. `AgentRegistry` — Agent Card parser + capability matcher. Fields: `_agents: dict[str, dict]`, `_lock`. Methods: `register(agent_id, card)`, `unregister(agent_id)`, `can_handle(agent_id, task_type) → bool`, `best_agent(task_type) → Optional[str]`, `list_agents()`.
5. `TaskOrchestrator` — fan-out/fan-in + pipeline execution. Methods: `fan_out(tasks, dispatch_fn) → list`, `pipeline(task, stages) → TaskRecord`.

**Architecture rules:**
- Pure Python stdlib only (no new pip imports)
- Dataclasses for all new components
- Thread-safe where state is shared (use threading.Lock)
- Append to existing file (do not rewrite)
- Follow existing code style (dataclasses, field(default_factory=...))

## Constraints
- Python 3.14+ syntax allowed
- All existing 34 tests MUST continue passing
- Each component needs its own test functions in test file
- Validation commands below MUST all pass — if any fail, fix before reporting
- Do NOT add dependencies — stdlib only (re, json, datetime, pathlib, hashlib, threading, dataclasses, typing, os)
- Keep code concise and readable, no over-engineering

## Exact Validation Commands

```bash
cd C:/Users/Admin/UGAFStudio

# 1. All tests must pass (original 34 + new)
PYTHONPATH=. python -m pytest qa_framework/tests/test_a2a_adapter.py -v

# 2. Type checking must pass
PYTHONPATH=. python -m mypy qa_framework/a2a_adapter.py

# 3. Linting must pass
PYTHONPATH=. python -m ruff check qa_framework/a2a_adapter.py qa_framework/tests/test_a2a_adapter.py

# 4. Git should show clean diff of only intended changes
git diff --stat
```

## Implementation Details

### TaskRecord dataclass
```python
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
```

### TaskStateMachine class
```python
class TaskStateMachine:
    """A2A Task lifecycle state machine."""
    
    def __init__(self):
        self.states = {"submitted", "working", "input-required", "completed", "failed", "canceled"}
        self._transitions = {
            "submitted": {"working", "canceled"},
            "working": {"completed", "failed", "input-required"},
            "input-required": {"working", "canceled"},
            "completed": set(),  # terminal
            "failed": set(),     # terminal
            "canceled": set(),   # terminal
        }
    
    def can_transition(self, from_state: str, to_state: str) -> bool:
        if from_state not in self.states or to_state not in self.states:
            return False
        return to_state in self._transitions.get(from_state, set())
```

### TaskSession dataclass
```python
@dataclass
class TaskSession:
    """Checkpoints running task state to disk for crash recovery."""
    session_id: str
    checkpoint_dir: str
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    def __post_init__(self):
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
```

### AgentRegistry dataclass
```python
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
```

### TaskOrchestrator dataclass
```python
@dataclass
class TaskOrchestrator:
    """Orchestrate multi-agent task execution patterns."""
    
    def fan_out(self, tasks: list[TaskRecord], dispatch_fn) -> list:
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
```

## Test Requirements (add to test_a2a_adapter.py)

```python
import tempfile
import os

# TaskRecord tests
def test_task_record_creation():
    t = TaskRecord(task_id="t1", task_type="qa_runner")
    assert t.status == "submitted"
    assert t.context_id is None
    assert t.history == []
    assert t.artifacts == []

def test_task_record_state_transitions():
    t = TaskRecord(task_id="t1")
    t.transition_to("working")
    assert t.status == "working"
    t.transition_to("completed")
    assert t.status == "completed"

def test_task_record_invalid_transition():
    t = TaskRecord(task_id="t1")
    try:
        t.transition_to("completed")  # Can't skip working
        assert False, "Should have raised"
    except ValueError:
        pass

# TaskStateMachine tests
def test_task_state_machine_graph():
    sm = TaskStateMachine()
    assert "submitted" in sm.states
    assert "working" in sm.states
    assert "input-required" in sm.states
    assert "completed" in sm.states
    assert "failed" in sm.states
    assert "canceled" in sm.states
    assert sm.can_transition("submitted", "working")
    assert sm.can_transition("submitted", "canceled")
    assert sm.can_transition("working", "completed")
    assert sm.can_transition("working", "failed")
    assert sm.can_transition("working", "input-required")
    assert sm.can_transition("input-required", "working")
    assert not sm.can_transition("completed", "working")
    assert not sm.can_transition("failed", "completed")

# TaskSession tests
def test_task_session_save_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        session = TaskSession(session_id="s1", checkpoint_dir=tmp)
        task = TaskRecord(task_id="t1", task_type="qa_runner")
        task.transition_to("working")
        session.save_checkpoint(task)
        assert os.path.exists(os.path.join(tmp, "s1_t1.json"))

def test_task_session_load_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        session = TaskSession(session_id="s1", checkpoint_dir=tmp)
        task = TaskRecord(task_id="t1", task_type="qa_runner")
        task.transition_to("working")
        session.save_checkpoint(task)
        loaded = session.load_checkpoint("t1")
        assert loaded.task_id == "t1"
        assert loaded.status == "working"

def test_task_session_auto_recovery():
    with tempfile.TemporaryDirectory() as tmp:
        session = TaskSession(session_id="s1", checkpoint_dir=tmp)
        task = TaskRecord(task_id="t1")
        task.transition_to("working")
        session.save_checkpoint(task)
        session2 = TaskSession(session_id="s1", checkpoint_dir=tmp)
        recoverable = session2.list_recoverable_tasks()
        assert len(recoverable) == 1
        assert recoverable[0].task_id == "t1"

# AgentRegistry tests
def test_agent_registry_register():
    reg = AgentRegistry()
    reg.register("unreal-specialist", {"skills": ["game_qa", "unreal_engine"], "capabilities": ["perception"]})
    assert reg.can_handle("unreal-specialist", "game_qa")
    assert not reg.can_handle("unreal-specialist", "security_audit")

def test_agent_registry_best_agent():
    reg = AgentRegistry()
    reg.register("agent1", {"skills": ["game_qa"]})
    reg.register("agent2", {"skills": ["game_qa", "security_audit"]})
    best = reg.best_agent("security_audit")
    assert best == "agent2"

def test_agent_registry_no_match():
    reg = AgentRegistry()
    reg.register("agent1", {"skills": ["game_qa"]})
    assert reg.best_agent("nonexistent") is None

# TaskOrchestrator tests
def test_orchestrator_fan_out():
    orch = TaskOrchestrator()
    tasks = [TaskRecord(task_id="t1"), TaskRecord(task_id="t2")]
    results = orch.fan_out(tasks, lambda t: (t.task_id, "completed"))
    assert len(results) == 2
    assert results[0] == ("t1", "completed")

def test_orchestrator_pipeline():
    orch = TaskOrchestrator()
    task = TaskRecord(task_id="t1")
    stages = [
        (lambda t: t.transition_to("working"), "working"),
        (lambda t: t.add_artifact("a1", "output"), "completed"),
    ]
    result = orch.pipeline(task, stages)
    assert result.status == "completed"
    assert len(result.artifacts) == 1
```

## Report Format
Reply with:
- Status: SUCCESS or FAILURE
- Components added: list of 5
- Tests added: count
- Validation results: pytest/mypy/ruff output summary
- Files changed: list
- Any issues or deviations

## Critical
- If validation commands fail, FIX the code before reporting success
- Do NOT disable or modify existing tests
- Do NOT add new pip dependencies
- If OpenCode goes off-task or starts reasoning instead of coding, STOP and report FAILURE with reason
