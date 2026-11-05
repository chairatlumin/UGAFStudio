import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class TraceRecord:
    task_id: str
    agent_id: str
    phase: str
    duration_ms: float
    success: bool
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class AgentTelemetry:
    def __init__(self, output_path: str = ".ai/telemetry/traces.jsonl", buffer_size: int = 10):
        self.output_path = output_path
        self.buffer_size = buffer_size
        self.buffer: list[TraceRecord] = []
        self._lock = threading.Lock()

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    def record(
        self,
        task_id: str,
        agent_id: str,
        phase: str,
        duration_ms: float,
        success: bool,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        record = TraceRecord(
            task_id=task_id,
            agent_id=agent_id,
            phase=phase,
            duration_ms=duration_ms,
            success=success,
            metadata=metadata or {},
        )

        with self._lock:
            self.buffer.append(record)
            if len(self.buffer) >= self.buffer_size:
                self._flush_unlocked()

    def flush(self) -> None:
        with self._lock:
            self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        if not self.buffer:
            return

        with open(self.output_path, 'a', encoding='utf-8') as f:
            for record in self.buffer:
                try:
                    f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
                except TypeError:
                    safe = {}
                    for k, v in asdict(record).items():
                        try:
                            json.dumps(v)
                            safe[k] = v
                        except TypeError:
                            safe[k] = str(v)
                    f.write(json.dumps(safe, ensure_ascii=False) + "\n")

        self.buffer.clear()

    def get_task_traces(self, task_id: str) -> list[dict]:
        traces: list[dict] = []
        if not os.path.exists(self.output_path):
            return traces
        with open(self.output_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get('task_id') == task_id:
                        traces.append(record)
                except json.JSONDecodeError:
                    continue
        return traces

    def summary(self) -> dict[str, Any]:
        stats = {
            'total_tasks': 0,
            'total_phases': 0,
            'success_rate': 0.0,
            'avg_duration_ms': 0.0,
            'failures': 0,
        }

        if not os.path.exists(self.output_path):
            return stats

        tasks = set()
        total = 0
        successes = 0
        durations = []

        with open(self.output_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    tasks.add(record.get('task_id'))
                    total += 1
                    if record.get('success'):
                        successes += 1
                    durations.append(record.get('duration_ms', 0))
                except json.JSONDecodeError:
                    continue

        stats['total_tasks'] = len(tasks)
        stats['total_phases'] = total
        if total > 0:
            stats['success_rate'] = successes / total
            stats['avg_duration_ms'] = sum(durations) / len(durations)
            stats['failures'] = total - successes

        return stats
