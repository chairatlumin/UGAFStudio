import pytest
from .orchestration_health import HealthCheck, HealthReport, MetricsCollector, MetricsReport, HealthStatus
from .graceful_shutdown import GracefulShutdown, ShutdownConfig
from .research_trajectory import ResearchTrajectory


class TestIntegrationHealthShutdown:
    def test_research_trajectory_has_required_attributes(self) -> None:
        rt = ResearchTrajectory()
        assert hasattr(rt, "health_check")
        assert hasattr(rt, "metrics_collector")
        assert hasattr(rt, "graceful_shutdown")

    def test_research_trajectory_get_health_report(self) -> None:
        rt = ResearchTrajectory()
        rt.health_check.register_check("check1", lambda: (True, "ok"))
        report = rt.get_health_report()
        assert isinstance(report, HealthReport)
        assert report.status == HealthStatus.HEALTHY

    def test_research_trajectory_get_metrics_report(self) -> None:
        rt = ResearchTrajectory()
        report = rt.get_metrics_report()
        assert isinstance(report, MetricsReport)

    def test_research_trajectory_record_request(self) -> None:
        rt = ResearchTrajectory()
        rt.record_request(success=True, latency_ms=150.5)
        rt.record_request(success=False, latency_ms=50.0)
        metrics_report = rt.get_metrics_report()
        assert metrics_report.total_requests == 2
        assert metrics_report.success_count == 1
        assert metrics_report.error_count == 1

    def test_research_trajectory_register_cleanup(self) -> None:
        rt = ResearchTrajectory()
        called = [False]

        def cleanup() -> None:
            called[0] = True

        rt.register_cleanup(cleanup)
        rt.shutdown()
        assert called[0] is True

    def test_research_trajectory_shutdown_idempotent(self) -> None:
        rt = ResearchTrajectory()
        call_count = [0]

        def cleanup() -> None:
            call_count[0] += 1

        rt.register_cleanup(cleanup)
        rt.shutdown()
        rt.shutdown()
        assert call_count[0] == 1

    def test_research_trajectory_integrated_usage(self) -> None:
        rt = ResearchTrajectory()
        rt.health_check.register_check("latency", lambda: (True, "ok"))
        rt.record_request(success=True, latency_ms=100.0)
        rt.record_request(success=True, latency_ms=200.0)

        health_report = rt.get_health_report()
        metrics_report = rt.get_metrics_report()

        assert health_report.status == HealthStatus.HEALTHY
        assert metrics_report.total_requests == 2
        assert metrics_report.success_rate == pytest.approx(1.0)
        assert metrics_report.avg_latency_ms == pytest.approx(150.0)

    def test_graceful_shutdown_config(self) -> None:
        gs = GracefulShutdown(ShutdownConfig(timeout_seconds=60.0, force_exit_on_timeout=True))
        assert gs._config.timeout_seconds == 60.0
        assert gs._config.force_exit_on_timeout is True