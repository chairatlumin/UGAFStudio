from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

from .orchestration_health import HealthCheck, HealthReport, MetricsCollector, MetricsReport
from .graceful_shutdown import GracefulShutdown, ShutdownConfig


@dataclass
class ResearchTrajectory:
    health_check: HealthCheck = field(default_factory=HealthCheck)
    metrics_collector: MetricsCollector = field(default_factory=MetricsCollector)
    graceful_shutdown: GracefulShutdown = field(
        default_factory=lambda: GracefulShutdown(ShutdownConfig())
    )

    def get_health_report(self) -> HealthReport:
        return self.health_check.run_checks()

    def get_metrics_report(self) -> MetricsReport:
        return self.metrics_collector.get_report()

    def record_request(self, success: bool, latency_ms: float = 0.0) -> None:
        self.metrics_collector.record_request(success, latency_ms)

    def register_cleanup(self, cleanup_func: Callable[[], None]) -> None:
        self.graceful_shutdown.register_cleanup(cleanup_func)

    def shutdown(self) -> None:
        self.graceful_shutdown.shutdown()