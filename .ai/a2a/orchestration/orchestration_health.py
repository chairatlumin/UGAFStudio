from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Callable, Dict, List, Optional, Tuple


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthReport:
    status: HealthStatus
    timestamp: float
    checks: Dict[str, dict] = field(default_factory=dict)
    message: str = ""


@dataclass
class MetricsReport:
    total_requests: int
    success_count: int
    error_count: int
    success_rate: float
    avg_latency_ms: float
    timestamp: float


class HealthCheck:
    def __init__(self) -> None:
        self._checks: List[Tuple[str, Callable[[], Tuple[bool, str]]]] = []
        self._running: bool = False

    def register_check(
        self, name: str, check_func: Callable[[], Tuple[bool, str]]
    ) -> None:
        self._checks.append((name, check_func))

    def run_checks(self) -> HealthReport:
        if self._running:
            return HealthReport(
                status=HealthStatus.UNHEALTHY,
                timestamp=monotonic(),
                checks={},
                message="Health check already running",
            )

        self._running = True
        checks: Dict[str, dict] = {}
        healthy_count = 0
        degraded_count = 0
        unhealthy_count = 0
        error_messages: List[str] = []

        for name, check_func in self._checks:
            try:
                success, detail = check_func()
                checks[name] = {"success": success, "detail": detail}
                if success:
                    healthy_count += 1
                elif detail.lower().find("degraded") >= 0:
                    degraded_count += 1
                    checks[name]["status"] = "degraded"
                else:
                    unhealthy_count += 1
                    error_messages.append(detail)
            except Exception as e:
                checks[name] = {"success": False, "detail": str(e)}
                unhealthy_count += 1
                error_messages.append(str(e))

        self._running = False

        if unhealthy_count > 0:
            status = HealthStatus.UNHEALTHY
            message = "; ".join(error_messages) if error_messages else "Unhealthy checks failed"
        elif degraded_count > 0:
            status = HealthStatus.DEGRADED
            message = f"{degraded_count} check(s) degraded"
        else:
            status = HealthStatus.HEALTHY
            message = "All checks passed"

        return HealthReport(
            status=status,
            timestamp=monotonic(),
            checks=checks,
            message=message,
        )


class MetricsCollector:
    def __init__(self) -> None:
        self._total_requests: int = 0
        self._success_count: int = 0
        self._error_count: int = 0
        self._total_latency_ms: float = 0.0

    def record_request(self, success: bool, latency_ms: float = 0.0) -> None:
        self._total_requests += 1
        if success:
            self._success_count += 1
        else:
            self._error_count += 1
        self._total_latency_ms += latency_ms

    def get_success_rate(self) -> float:
        if self._total_requests == 0:
            return 0.0
        return self._success_count / self._total_requests

    def get_avg_latency_ms(self) -> float:
        if self._total_requests == 0:
            return 0.0
        return self._total_latency_ms / self._total_requests

    def get_report(self) -> MetricsReport:
        return MetricsReport(
            total_requests=self._total_requests,
            success_count=self._success_count,
            error_count=self._error_count,
            success_rate=self.get_success_rate(),
            avg_latency_ms=self.get_avg_latency_ms(),
            timestamp=monotonic(),
        )