import json
import os
import tempfile

from qa_framework.secure_observe.telemetry import AgentTelemetry, TraceRecord


def test_trace_record_creation():
    record = TraceRecord(
        task_id="t1",
        agent_id="agent-1",
        phase="dispatch",
        duration_ms=100.0,
        success=True,
        metadata={"command": "opencode run ..."},
    )
    assert record.task_id == "t1"
    assert record.success
    assert record.timestamp > 0


def test_telemetry_writes_jsonl():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        path = f.name

    try:
        telemetry = AgentTelemetry(output_path=path, buffer_size=1)
        telemetry.record(task_id="t1", agent_id="a1", phase="dispatch", duration_ms=50.0, success=True)
        telemetry.record(task_id="t1", agent_id="a1", phase="execution", duration_ms=500.0, success=True)
        telemetry.flush()

        with open(path, 'r') as f:
            lines = f.readlines()

        assert len(lines) == 2
        record = json.loads(lines[0])
        assert record['task_id'] == "t1"
        assert record['phase'] == "dispatch"
        assert record['success'] is True
    finally:
        os.unlink(path)


def test_telemetry_buffer_auto_flush():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        path = f.name

    try:
        telemetry = AgentTelemetry(output_path=path, buffer_size=2)
        telemetry.record(task_id="t1", agent_id="a1", phase="dispatch", duration_ms=50.0, success=True)
        # Buffer not yet full
        with open(path, 'r') as f:
            assert len(f.readlines()) == 0

        telemetry.record(task_id="t1", agent_id="a1", phase="execution", duration_ms=500.0, success=True)
        # Buffer full — auto-flush
        with open(path, 'r') as f:
            assert len(f.readlines()) == 2
    finally:
        os.unlink(path)


def test_get_task_traces():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        path = f.name

    try:
        telemetry = AgentTelemetry(output_path=path, buffer_size=1)
        telemetry.record(task_id="t1", agent_id="a1", phase="dispatch", duration_ms=50.0, success=True)
        telemetry.record(task_id="t2", agent_id="a2", phase="dispatch", duration_ms=60.0, success=True)

        traces = telemetry.get_task_traces("t1")
        assert len(traces) == 1
        assert traces[0]['task_id'] == "t1"
    finally:
        os.unlink(path)


def test_summary():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        path = f.name

    try:
        telemetry = AgentTelemetry(output_path=path, buffer_size=1)
        telemetry.record(task_id="t1", agent_id="a1", phase="dispatch", duration_ms=100.0, success=True)
        telemetry.record(task_id="t1", agent_id="a1", phase="execution", duration_ms=200.0, success=False)
        telemetry.record(task_id="t2", agent_id="a2", phase="dispatch", duration_ms=300.0, success=True)

        stats = telemetry.summary()
        assert stats['total_tasks'] == 2
        assert stats['total_phases'] == 3
        assert stats['failures'] == 1
        assert stats['success_rate'] == 2 / 3
        assert stats['avg_duration_ms'] == 200.0
    finally:
        os.unlink(path)
