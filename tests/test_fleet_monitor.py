"""Tests for FleetRecorder and FleetMonitor."""

from __future__ import annotations

import os
import tempfile

import pytest

from qa_framework.fleet_monitor import FleetMonitor, FleetRecorder


class TestFleetRecorder:
    """Test FleetRecorder SQLite backend."""

    def test_fleet_recorder_records_dispatch(self) -> None:
        """Recording a dispatch returns a valid row ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            rec = FleetRecorder(db_path=db_path)
            row_id = rec.record_dispatch(
                agent_id="agent-1",
                task_type="opencode_dispatch",
                model="opencode/nemotron-3.5-lightning-free",
                success=True,
                duration_ms=1500,
                cost_usd=0.02,
                confidence=0.85,
            )
            assert row_id > 0
            rec.close()

    def test_fleet_recorder_returns_metrics(self) -> None:
        """get_agent_metrics returns correct aggregate values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            rec = FleetRecorder(db_path=db_path)
            rec.record_dispatch("a1", "task", "m", True, 100, 0.01, 0.9)
            rec.record_dispatch("a1", "task", "m", False, 200, 0.02, 0.5)
            rec.record_dispatch("a1", "task", "m", True, 300, 0.015, 0.8)

            metrics = rec.get_agent_metrics("a1")
            assert metrics["agent_id"] == "a1"
            assert metrics["total_dispatches"] == 3
            assert metrics["success_rate"] == pytest.approx(2 / 3, abs=0.01)
            assert metrics["avg_latency_ms"] == pytest.approx(200.0, abs=0.1)
            assert metrics["total_cost_usd"] == pytest.approx(0.045, abs=0.001)
            rec.close()

    def test_get_all_agents(self) -> None:
        """get_all_agents returns all unique agent IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            rec = FleetRecorder(db_path=db_path)
            rec.record_dispatch("a1", "task", "m", True, 100)
            rec.record_dispatch("a2", "task", "m", True, 100)
            rec.record_dispatch("a1", "task", "m", True, 200)

            agents = rec.get_all_agents()
            assert sorted(agents) == ["a1", "a2"]
            rec.close()

    def test_prune_old_records(self) -> None:
        """prune_old_records removes old entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            rec = FleetRecorder(db_path=db_path)
            rec.record_dispatch("a1", "task", "m", True, 100)
            conn = rec.get_conn()
            conn.execute("INSERT INTO dispatch_events "
                         "(agent_id, task_type, model, success, duration_ms, timestamp) "
                         "VALUES ('a1', 'task', 'm', 1, 100, "
                         "datetime('now', '-60 days'))")
            conn.commit()

            deleted = rec.prune_old_records(max_age_days=30)
            assert deleted == 1
            rec.close()


class TestFleetMonitor:
    """Test FleetMonitor aggregate queries."""

    def test_fleet_summary(self) -> None:
        """Fleet summary returns aggregate stats across all agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            rec = FleetRecorder(db_path=db_path)
            rec.record_dispatch("a1", "task", "m", True, 100, 0.01, 0.9)
            rec.record_dispatch("a1", "task", "m", False, 200, 0.02, 0.5)
            rec.record_dispatch("a2", "task", "m", True, 50, 0.005, 0.95)

            mon = FleetMonitor(rec)
            summary = mon.get_fleet_summary()
            assert summary["total_agents"] == 2
            assert summary["total_dispatches"] == 3
            assert summary["fleet_success_rate"] == pytest.approx(2 / 3, abs=0.01)
            assert summary["total_cost_usd"] == pytest.approx(0.035, abs=0.001)
            rec.close()

    def test_anomaly_detection(self) -> None:
        """Anomaly detection finds agents with high error rates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            rec = FleetRecorder(db_path=db_path)
            for _ in range(10):
                rec.record_dispatch("a1", "task", "m", False, 5000, 0.1, 0.2)

            mon = FleetMonitor(rec)
            anomalies = mon.get_anomalies(max_error_rate=0.3, min_samples=5)
            assert len(anomalies) == 1
            assert anomalies[0]["agent_id"] == "a1"
            assert anomalies[0]["error_rate"] == pytest.approx(1.0)
            rec.close()

    def test_top_cost_agents(self) -> None:
        """Top cost agents sorted by total cost."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            rec = FleetRecorder(db_path=db_path)
            rec.record_dispatch("a1", "task", "m", True, 100, 1.0)
            rec.record_dispatch("a1", "task", "m", True, 100, 0.5)
            rec.record_dispatch("a2", "task", "m", True, 100, 2.0)

            mon = FleetMonitor(rec)
            top = mon.get_top_cost_agents(limit=5)
            assert top[0]["agent_id"] == "a2"
            rec.close()

    def test_latency_percentiles(self) -> None:
        """Latency percentiles computed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            rec = FleetRecorder(db_path=db_path)
            latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
            for lat in latencies:
                rec.record_dispatch("a1", "task", "m", True, lat)

            mon = FleetMonitor(rec)
            percs = mon.get_latency_percentiles("a1")
            assert percs["p50"] == pytest.approx(55.0, abs=5.0)
            assert percs["p90"] >= 90.0
            rec.close()

    def test_health_report(self) -> None:
        """Health report includes all expected sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            rec = FleetRecorder(db_path=db_path)
            for _ in range(10):
                rec.record_dispatch("a1", "task", "m", False, 5000, 0.1)

            mon = FleetMonitor(rec)
            report = mon.generate_health_report()
            assert "summary" in report
            assert "anomalies" in report
            assert "alerts" in report
            assert report["alerts"][0]["severity"] == "warning"
            rec.close()
