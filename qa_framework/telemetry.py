"""OTel-based telemetry with GenAI semantic conventions for UGAFStudio.

Provides:
- TelemetryProvider: OTel TracerProvider wrapper with graceful degradation (no-op when
  opentelemetry-sdk is not installed)
- BudgetEnforcer: inline token/cost budget enforcement with ALLOW/DOWNGRADE/CIRCUIT_BREAK
- SpanHierarchy: tracks span tree for a single agent run (llm_call, tool_call, etc.)
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generator

# Optional OTel import — graceful degradation
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


class SpanKind(str, Enum):
    """Agent-specific span kinds (AgentTelemetry 2026 spec)."""

    AGENT = "agent"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    PLANNING = "planning"
    RETRIEVAL = "retrieval"
    GUARD_RAIL = "guard_rail"
    DELEGATION = "delegation"
    MEMORY = "memory"


@dataclass
class TelemetryProvider:
    """OTel TracerProvider wrapper with graceful degradation.

    When opentelemetry-sdk is installed, provides real tracing.
    When not installed, all methods are safe no-ops.
    """

    service_name: str = "ugafstudio-agent"
    console: bool = True
    otlp_endpoint: str | None = None
    _tracer: Any = field(default=None, init=False, repr=False)
    _available: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not OTEL_AVAILABLE:
            self._available = False
            return
        resource = Resource.create({SERVICE_NAME: self.service_name})
        provider = SDKTracerProvider(resource=resource)
        if self.otlp_endpoint:
            processor = BatchSpanProcessor(_NoopExporter())
        else:
            processor = SimpleSpanProcessor(
                _ConsoleSpanExporter() if self.console else _NoopExporter()
            )
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer(self.service_name)
        self._available = True

    def is_available(self) -> bool:
        return self._available

    @contextmanager
    def start_span(
        self, name: str, kind: SpanKind, **attributes: Any
    ) -> Generator[Any, None, None]:
        """Start a span with GenAI semantic conventions."""
        if not self._available or self._tracer is None:
            yield _NoopSpan()
            return
        with self._tracer.start_as_current_span(name) as span:
            span.set_attribute("gen_ai.agent.name", self.service_name)
            span.set_attribute("gen_ai.operation.name", kind.value)
            for k, v in attributes.items():
                span.set_attribute(k, v)
            yield span


@dataclass
class BudgetEnforcer:
    """Inline budget enforcer with context propagation pattern.

    Tracks cumulative token/cost usage and enforces limits.
    Returns: ALLOW | DOWNGRADE | CIRCUIT_BREAK
    """

    max_tokens: int = 10000
    max_cost_usd: float = 0.50
    _spent_tokens: int = 0
    _spent_cost: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def can_spend(self, estimated_tokens: int, estimated_cost: float) -> bool:
        with self._lock:
            return (
                self._spent_tokens + estimated_tokens <= self.max_tokens
                and self._spent_cost + estimated_cost <= self.max_cost_usd
            )

    def spend(self, tokens: int, cost_usd: float) -> None:
        with self._lock:
            self._spent_tokens += tokens
            self._spent_cost += cost_usd

    @property
    def remaining_tokens(self) -> int:
        with self._lock:
            return self.max_tokens - self._spent_tokens

    @property
    def remaining_cost(self) -> float:
        with self._lock:
            return round(self.max_cost_usd - self._spent_cost, 6)

    def check_action(self, estimated_tokens: int, estimated_cost: float) -> str:
        """Return ALLOW, DOWNGRADE, or CIRCUIT_BREAK."""
        with self._lock:
            if self._spent_tokens + estimated_tokens > self.max_tokens:
                return "CIRCUIT_BREAK"
            if self._spent_cost + estimated_cost > self.max_cost_usd:
                return "CIRCUIT_BREAK"
            if self._spent_tokens + estimated_tokens > int(self.max_tokens * 0.8):
                return "DOWNGRADE"
            if self._spent_cost + estimated_cost > self.max_cost_usd * 0.8:
                return "DOWNGRADE"
            return "ALLOW"

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "max_tokens": self.max_tokens,
                "spent_tokens": self._spent_tokens,
                "remaining_tokens": self.max_tokens - self._spent_tokens,
                "max_cost_usd": self.max_cost_usd,
                "spent_cost_usd": round(self._spent_cost, 6),
                "remaining_cost_usd": round(
                    self.max_cost_usd - self._spent_cost, 6
                ),
                "utilization": round(self._spent_tokens / self.max_tokens, 4)
                if self.max_tokens > 0
                else 0.0,
            }


@dataclass
class SpanHierarchy:
    """Track span hierarchy for a single agent run.

    When OTel is available, emits real spans.
    When not available, tracks in-memory for JSONL export.
    """

    agent_name: str
    trace_id: str | None = None
    _spans: list[dict[str, Any]] = field(default_factory=list)
    _active_llm_call: dict[str, Any] | None = field(default=None, repr=False)
    _active_tool_call: dict[str, Any] | None = field(default=None, repr=False)
    _start_time: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if self.trace_id is None:
            self.trace_id = f"trace-{int(time.time() * 1000)}"
        self._start_time = time.time()

    def start_llm_call(self, model: str, **attrs: Any) -> None:
        self._active_llm_call = {
            "model": model,
            "start_time": time.time(),
            **attrs,
        }

    def end_llm_call(
        self,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        finish_reason: str = "stop",
    ) -> None:
        if self._active_llm_call is None:
            return
        record = {
            **self._active_llm_call,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "finish_reason": finish_reason,
            "elapsed_ms": round(
                (time.time() - self._active_llm_call["start_time"]) * 1000, 2
            ),
        }
        self._spans.append({"kind": SpanKind.LLM_CALL, **record})
        self._active_llm_call = None

    def start_tool_call(self, tool_name: str, **attrs: Any) -> None:
        self._active_tool_call = {
            "tool_name": tool_name,
            "start_time": time.time(),
            **attrs,
        }

    def end_tool_call(self, success: bool, error: str = "") -> None:
        if self._active_tool_call is None:
            return
        record = {
            **self._active_tool_call,
            "success": success,
            "error": error,
            "elapsed_ms": round(
                (time.time() - self._active_tool_call["start_time"]) * 1000, 2
            ),
        }
        self._spans.append({"kind": SpanKind.TOOL_CALL, **record})
        self._active_tool_call = None

    def add_memory_span(self, task_id: str, used_memory: bool, outcome: str) -> None:
        """Record a memory access span."""
        self._spans.append(
            {
                "kind": SpanKind.MEMORY,
                "task_id": task_id,
                "used_memory": used_memory,
                "outcome": outcome,
                "timestamp": time.time(),
            }
        )

    @property
    def total_spans(self) -> int:
        return len(self._spans)

    @property
    def total_llm_calls(self) -> int:
        return sum(1 for s in self._spans if s.get("kind") == SpanKind.LLM_CALL)

    @property
    def total_tool_calls(self) -> int:
        return sum(1 for s in self._spans if s.get("kind") == SpanKind.TOOL_CALL)

    @property
    def total_tokens_in(self) -> int:
        return sum(
            s.get("tokens_in", 0)
            for s in self._spans
            if s.get("kind") == SpanKind.LLM_CALL
        )

    @property
    def total_tokens_out(self) -> int:
        return sum(
            s.get("tokens_out", 0)
            for s in self._spans
            if s.get("kind") == SpanKind.LLM_CALL
        )

    @property
    def total_cost_usd(self) -> float:
        return round(
            sum(
                s.get("cost_usd", 0.0)
                for s in self._spans
                if s.get("kind") == SpanKind.LLM_CALL
            ),
            6,
        )

    def finish(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "trace_id": self.trace_id,
            "total_spans": len(self._spans),
            "total_llm_calls": self.total_llm_calls,
            "total_tool_calls": self.total_tool_calls,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_cost_usd": self.total_cost_usd,
            "elapsed_ms": round((time.time() - self._start_time) * 1000, 2),
            "spans": self._spans,
        }


# ---------------------------------------------------------------------------
# OTel exporters
# ---------------------------------------------------------------------------


class _ConsoleSpanExporter:
    """Minimal console exporter for local dev."""

    def export(self, spans) -> None:
        for span in spans:
            print(f"[SPAN] {span.name} {dict(span.attributes)}")

    def shutdown(self) -> None:
        pass


class _NoopExporter:
    """No-op exporter when OTel installed but tracing disabled."""

    def export(self, spans) -> None:
        pass

    def shutdown(self) -> None:
        pass


class _NoopSpan:
    """No-op span for when OTel is not available."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, *args, **kwargs) -> None:
        pass

    def record_exception(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
