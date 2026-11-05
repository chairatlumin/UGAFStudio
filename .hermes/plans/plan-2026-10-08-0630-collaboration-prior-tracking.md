# Collaboration Prior Tracking Implementation Plan
> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add collaboration prior tracking to learn from successful agent handoffs and improve future orchestration.

**Architecture:** Extend the existing A2A task graph system with a collaboration tracker that records successful agent handoff patterns, stores them in SQLite, and provides querying capabilities for optimal agent selection.

**Tech Stack:** Python 3.14, Pydantic, SQLite, pytest

---

## Current Context

- A2A task graph decomposition implemented and tested
- TaskGraphManager handles DAG creation and validation
- ValidationGateExecutor validates outputs between stages
- No tracking of successful agent handoff patterns
- No learning from historical task execution

## Proposed Approach

1. **Collaboration Prior Model**: Define data model for tracking agent collaborations
2. **Collaboration Tracker**: Implement tracking and querying logic
3. **SQLite Storage**: Persist collaboration data
4. **Integration**: Connect with TaskGraphManager for automatic tracking

---

## Task 1: Create Collaboration Prior Data Model

**Objective:** Define Pydantic models for collaboration priors.

**Files:**
- Create: `C:/Users/Admin/UGAFStudio/qa_framework/a2a/collaboration_prior.py`

**Step 1: Write failing test**

```python
# tests/a2a/test_collaboration_prior.py
from qa_framework.a2a.collaboration_prior import CollaborationPrior, CollaborationResult

def test_collaboration_prior_creation():
    prior = CollaborationPrior(
        task_type="code_generation",
        source_agent="hermes",
        target_agent="opencode",
        success_count=10,
        failure_count=2,
        avg_execution_time=5.5
    )
    assert prior.task_type == "code_generation"
    assert prior.source_agent == "hermes"
    assert prior.target_agent == "opencode"
    assert prior.success_rate == 10 / 12

def test_collaboration_result_creation():
    result = CollaborationResult(
        task_id="task-123",
        source_agent="hermes",
        target_agent="opencode",
        success=True,
        execution_time=3.2
    )
    assert result.task_id == "task-123"
    assert result.success == True
```

**Step 2: Run test to verify failure**

Run: `cd C:/Users/Admin/UGAFStudio && python -m pytest tests/a2a/test_collaboration_prior.py -v`
Expected: FAIL — "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# qa_framework/a2a/collaboration_prior.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class CollaborationPrior(BaseModel):
    task_type: str
    source_agent: str
    target_agent: str
    success_count: int = 0
    failure_count: int = 0
    avg_execution_time: float = 0.0
    last_used: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

class CollaborationResult(BaseModel):
    task_id: str
    source_agent: str
    target_agent: str
    success: bool
    execution_time: float
    timestamp: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = None
```

**Step 4: Run test to verify pass**

Run: `cd C:/Users/Admin/UGAFStudio && python -m pytest tests/a2a/test_collaboration_prior.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add qa_framework/a2a/collaboration_prior.py tests/a2a/test_collaboration_prior.py
git commit -m "feat(a2a): add collaboration prior data model"
```

---

## Task 2: Implement Collaboration Tracker

**Objective:** Create a tracker class to record and query collaboration patterns.

**Files:**
- Create: `C:/Users/Admin/UGAFStudio/qa_framework/a2a/collaboration_tracker.py`

**Step 1: Write failing test**

```python
# tests/a2a/test_collaboration_tracker.py
from qa_framework.a2a.collaboration_tracker import CollaborationTracker
from qa_framework.a2a.collaboration_prior import CollaborationResult

def test_tracker_records_success():
    tracker = CollaborationTracker(db_path=":memory:")
    result = CollaborationResult(
        task_id="task-1",
        source_agent="hermes",
        target_agent="opencode",
        success=True,
        execution_time=2.5
    )
    tracker.record(result)
    priors = tracker.get_priors("hermes", "opencode")
    assert len(priors) == 1
    assert priors[0].success_count == 1

def test_tracker_records_failure():
    tracker = CollaborationTracker(db_path=":memory:")
    result = CollaborationResult(
        task_id="task-2",
        source_agent="hermes",
        target_agent="opencode",
        success=False,
        execution_time=1.0,
        error_message="timeout"
    )
    tracker.record(result)
    priors = tracker.get_priors("hermes", "opencode")
    assert len(priors) == 1
    assert priors[0].failure_count == 1

def test_tracker_suggests_best_agent():
    tracker = CollaborationTracker(db_path=":memory:")
    # Record multiple results
    for i in range(5):
        tracker.record(CollaborationResult(
            task_id=f"task-{i}",
            source_agent="hermes",
            target_agent="opencode",
            success=True,
            execution_time=2.0
        ))
    for i in range(3):
        tracker.record(CollaborationResult(
            task_id=f"task-fail-{i}",
            source_agent="hermes",
            target_agent="other_agent",
            success=False,
            execution_time=1.0
        ))
    best = tracker.suggest_best_agent("hermes", ["opencode", "other_agent"])
    assert best == "opencode"
```

**Step 2: Run test to verify failure**

Run: `cd C:/Users/Admin/UGAFStudio && python -m pytest tests/a2a/test_collaboration_tracker.py -v`
Expected: FAIL — "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# qa_framework/a2a/collaboration_tracker.py
import sqlite3
from typing import List, Optional
from datetime import datetime
from .collaboration_prior import CollaborationPrior, CollaborationResult

class CollaborationTracker:
    def __init__(self, db_path: str = "collaboration_priors.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collaboration_priors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT,
                    source_agent TEXT,
                    target_agent TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    avg_execution_time REAL DEFAULT 0.0,
                    last_used TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collaboration_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    source_agent TEXT,
                    target_agent TEXT,
                    success BOOLEAN,
                    execution_time REAL,
                    timestamp TIMESTAMP,
                    error_message TEXT
                )
            """)
    
    def record(self, result: CollaborationResult):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO collaboration_results 
                (task_id, source_agent, target_agent, success, execution_time, timestamp, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (result.task_id, result.source_agent, result.target_agent,
                  result.success, result.execution_time, result.timestamp, result.error_message))
            
            # Update or insert prior
            cursor = conn.execute("""
                SELECT id, success_count, failure_count, avg_execution_time
                FROM collaboration_priors
                WHERE source_agent = ? AND target_agent = ?
            """, (result.source_agent, result.target_agent))
            row = cursor.fetchone()
            
            if row:
                prior_id, success_count, failure_count, avg_time = row
                if result.success:
                    success_count += 1
                else:
                    failure_count += 1
                total = success_count + failure_count
                new_avg = (avg_time * (total - 1) + result.execution_time) / total
                conn.execute("""
                    UPDATE collaboration_priors
                    SET success_count = ?, failure_count = ?, avg_execution_time = ?, last_used = ?
                    WHERE id = ?
                """, (success_count, failure_count, new_avg, result.timestamp, prior_id))
            else:
                conn.execute("""
                    INSERT INTO collaboration_priors
                    (task_type, source_agent, target_agent, success_count, failure_count, avg_execution_time, last_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, ("default", result.source_agent, result.target_agent,
                      1 if result.success else 0, 0 if result.success else 1,
                      result.execution_time, result.timestamp))
    
    def get_priors(self, source_agent: str, target_agent: str) -> List[CollaborationPrior]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT task_type, source_agent, target_agent, success_count, failure_count, avg_execution_time, last_used
                FROM collaboration_priors
                WHERE source_agent = ? AND target_agent = ?
            """, (source_agent, target_agent))
            rows = cursor.fetchall()
            return [CollaborationPrior(
                task_type=row[0],
                source_agent=row[1],
                target_agent=row[2],
                success_count=row[3],
                failure_count=row[4],
                avg_execution_time=row[5],
                last_used=row[6]
            ) for row in rows]
    
    def suggest_best_agent(self, source_agent: str, candidates: List[str]) -> Optional[str]:
        best_agent = None
        best_rate = -1.0
        for candidate in candidates:
            priors = self.get_priors(source_agent, candidate)
            if priors:
                rate = priors[0].success_rate
                if rate > best_rate:
                    best_rate = rate
                    best_agent = candidate
        return best_agent
```

**Step 4: Run test to verify pass**

Run: `cd C:/Users/Admin/UGAFStudio && python -m pytest tests/a2a/test_collaboration_tracker.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add qa_framework/a2a/collaboration_tracker.py tests/a2a/test_collaboration_tracker.py
git commit -m "feat(a2a): add collaboration tracker"
```

---

## Task 3: Integrate with TaskGraphManager

**Objective:** Add automatic collaboration tracking to TaskGraphManager.

**Files:**
- Modify: `C:/Users/Admin/UGAFStudio/qa_framework/a2a/task_graph_manager.py`

**Step 1: Add tracker initialization**

```python
# Add to task_graph_manager.py
from .collaboration_tracker import CollaborationTracker

class TaskGraphManager:
    def __init__(self):
        self.graph = TaskGraph()
        self.tracker = CollaborationTracker()
```

**Step 2: Record collaboration on node completion**

```python
# Add method to TaskGraphManager
def complete_node(self, node_id: str, output: str, success: bool = True):
    node = self.get_node(node_id)
    if node:
        node.status = NodeStatus.COMPLETED if success else NodeStatus.FAILED
        node.output = output
        # Record collaboration
        if node.dependencies:
            for dep_id in node.dependencies:
                dep_node = self.get_node(dep_id)
                if dep_node:
                    result = CollaborationResult(
                        task_id=node_id,
                        source_agent=dep_node.agent,
                        target_agent=node.agent,
                        success=success,
                        execution_time=0.0  # TODO: track actual time
                    )
                    self.tracker.record(result)
```

**Step 3: Run existing tests to verify no regression**

Run: `cd C:/Users/Admin/UGAFStudio && python -m pytest tests/a2a/test_task_graph_manager.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add qa_framework/a2a/task_graph_manager.py
git commit -m "feat(a2a): integrate collaboration tracking with task graph manager"
```

---

## Risks & Tradeoffs

- **Storage overhead**: SQLite database adds storage requirements
- **Performance**: Querying priors adds latency to task dispatch
- **Privacy**: Collaboration data may contain sensitive information

## Open Questions

- Should we add more sophisticated learning algorithms?
- How to handle concept drift in collaboration patterns?
- Should we share priors across different task types?
