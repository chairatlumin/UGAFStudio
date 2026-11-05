import pytest
from .orchestration_health import HealthStatus, HealthCheck, HealthReport, MetricsCollector, MetricsReport


class TestHealthStatus:
    def test_enum_values(self) -> None:
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


class TestHealthCheck:
    def test_register_check(self) -> None:
        hc = HealthCheck()
        hc.register_check("test_check", lambda: (True, "ok"))
        assert len(hc._checks) == 1

    def test_run_checks_healthy(self) -> None:
        hc = HealthCheck()
        hc.register_check("check1", lambda: (True, "ok"))
        hc.register_check("check2", lambda: (True, "ok"))
        report = hc.run_checks()
        assert report.status == HealthStatus.HEALTHY
        assert report.checks["check1"]["success"] is True

    def test_run_checks_unhealthy(self) -> None:
        hc = HealthCheck()
        hc.register_check("check1", lambda: (False, "error"))
        report = hc.run_checks()
        assert report.status == HealthStatus.UNHEALTHY

    def test_run_checks_degraded(self) -> None:
        hc = HealthCheck()
        hc.register_check("check1", lambda: (False, "degraded performance"))
        report = hc.run_checks()
        assert report.status == HealthStatus.DEGRADED

    def test_run_checks_with_exception(self) -> None:
        hc = HealthCheck()
        hc.register_check("bad_check", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        report = hc.run_checks()
        assert report.status == HealthStatus.UNHEALTHY


class TestMetricsCollector:
    def test_record_request(self) -> None:
        mc = MetricsCollector()
        mc.record_request(success=True, latency_ms=100.0)
        mc.record_request(success=True, latency_ms=200.0)
        mc.record_request(success=False, latency_ms=50.0)

    def test_get_success_rate(self) -> None:
        mc = MetricsCollector()
        mc.record_request(success=True)
        mc.record_request(success=True)
        mc.record_request(success=False)
        assert mc.get_success_rate() == pytest.approx(2 / 3)

    def test_get_success_rate_zero(self) -> None:
        mc = MetricsCollector()
        assert mc.get_success_rate() == 0.0

    def test_get_avg_latency_ms(self) -> None:
        mc = MetricsCollector()
        mc.record_request(success=True, latency_ms=100.0)
        mc.record_request(success=True, latency_ms=200.0)
        assert mc.get_avg_latency_ms() == pytest.approx(150.0)

    def test_get_avg_latency_ms_zero(self) -> None:
        mc = MetricsCollector()
        assert mc.get_avg_latency_ms() == 0.0

    def test_get_report(self) -> None:
        mc = MetricsCollector()
        mc.record_request(success=True, latency_ms=100.0)
        mc.record_request(success=False, latency_ms=50.0)
        report = mc.get_report()
        assert report.total_requests == 2
        assert report.success_count == 1
        assert report.error_count == 1
        assert report.success_rate == pytest.approx(0.5)
        assert report.avg_latency_ms == pytest.approx(75.0)
        assert isinstance(report.timestamp, float)