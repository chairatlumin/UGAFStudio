"""Tests for telemetry.py — TelemetryProvider, BudgetEnforcer, SpanHierarchy."""



from qa_framework.telemetry import (
    BudgetEnforcer,
    SpanHierarchy,
    SpanKind,
    TelemetryProvider,
)


class TestTelemetryProvider:
    def test_create_provider(self):
        tp = TelemetryProvider(service_name="test", console=False)
        # Should not crash regardless of OTel availability
        assert tp.is_available() is True or tp.is_available() is False

    def test_noop_span_context_manager(self):
        tp = TelemetryProvider(service_name="test", console=False)
        with tp.start_span("test_op", SpanKind.AGENT) as span:
            # Should not crash
            span.set_attribute("key", "value")


class TestBudgetEnforcer:
    def test_can_spend_within_budget(self):
        be = BudgetEnforcer(max_tokens=100, max_cost_usd=0.05)
        assert be.can_spend(50, 0.02) is True

    def test_cannot_spend_exceeds_token_budget(self):
        be = BudgetEnforcer(max_tokens=100, max_cost_usd=0.05)
        assert be.can_spend(101, 0.0) is False

    def test_cannot_spend_exceeds_cost_budget(self):
        be = BudgetEnforcer(max_tokens=100, max_cost_usd=0.05)
        assert be.can_spend(50, 0.06) is False

    def test_spend_updates_remaining(self):
        be = BudgetEnforcer(max_tokens=100, max_cost_usd=0.05)
        be.spend(30, 0.01)
        assert be.remaining_tokens == 70
        assert be.remaining_cost == 0.04

    def test_check_action_allow(self):
        be = BudgetEnforcer(max_tokens=100, max_cost_usd=0.05)
        assert be.check_action(10, 0.005) == "ALLOW"

    def test_check_action_downgrade_token(self):
        be = BudgetEnforcer(max_tokens=100, max_cost_usd=0.05)
        # 81 tokens = 81% of 100, over 80% threshold
        assert be.check_action(81, 0.001) == "DOWNGRADE"

    def test_check_action_downgrade_cost(self):
        be = BudgetEnforcer(max_tokens=100, max_cost_usd=0.05)
        # $0.041 = 82% of 0.05, over 80% threshold
        assert be.check_action(1, 0.041) == "DOWNGRADE"

    def test_check_action_circuit_break_token(self):
        be = BudgetEnforcer(max_tokens=100, max_cost_usd=0.05)
        be.spend(90, 0.0)
        # 20 more tokens would exceed 100
        assert be.check_action(20, 0.0) == "CIRCUIT_BREAK"

    def test_check_action_circuit_break_cost(self):
        be = BudgetEnforcer(max_tokens=100, max_cost_usd=0.05)
        be.spend(0, 0.04)
        # 0.02 more cost would exceed 0.05
        assert be.check_action(0, 0.02) == "CIRCUIT_BREAK"

    def test_summary(self):
        be = BudgetEnforcer(max_tokens=100, max_cost_usd=0.05)
        be.spend(30, 0.01)
        summary = be.summary()
        assert summary["max_tokens"] == 100
        assert summary["spent_tokens"] == 30
        assert summary["remaining_tokens"] == 70
        assert summary["max_cost_usd"] == 0.05
        assert summary["spent_cost_usd"] == 0.01
        assert summary["utilization"] == 0.3


class TestSpanHierarchy:
    def test_create_hierarchy(self):
        h = SpanHierarchy(agent_name="test-agent", trace_id="abc123")
        assert h.agent_name == "test-agent"
        assert h.trace_id == "abc123"

    def test_auto_trace_id(self):
        h = SpanHierarchy(agent_name="test-agent")
        assert h.trace_id is not None
        assert h.trace_id.startswith("trace-")

    def test_start_end_llm_call(self):
        h = SpanHierarchy(agent_name="test-agent")
        h.start_llm_call(model="nemotron")
        h.end_llm_call(tokens_in=100, tokens_out=50, cost_usd=0.001)
        assert h.total_llm_calls == 1

    def test_start_end_tool_call(self):
        h = SpanHierarchy(agent_name="test-agent")
        h.start_tool_call(tool_name="file_read")
        h.end_tool_call(success=True)
        assert h.total_tool_calls == 1

    def test_add_memory_span(self):
        h = SpanHierarchy(agent_name="test-agent")
        h.add_memory_span(task_id="task-1", used_memory=True, outcome="pass")
        assert h.total_spans == 1

    def test_finish_summary(self):
        h = SpanHierarchy(agent_name="test-agent", trace_id="t1")
        h.start_llm_call(model="nemotron")
        h.end_llm_call(tokens_in=100, tokens_out=50, cost_usd=0.001)
        h.start_tool_call(tool_name="file_read")
        h.end_tool_call(success=True)
        summary = h.finish()
        assert summary["agent_name"] == "test-agent"
        assert summary["trace_id"] == "t1"
        assert summary["total_spans"] == 2
        assert summary["total_llm_calls"] == 1
        assert summary["total_tool_calls"] == 1
        assert summary["total_tokens_in"] == 100
        assert summary["total_tokens_out"] == 50
        assert summary["total_cost_usd"] == 0.001

    def test_no_active_llm_call(self):
        h = SpanHierarchy(agent_name="test-agent")
        h.end_llm_call(tokens_in=100, tokens_out=50, cost_usd=0.001)
        assert h.total_llm_calls == 0

    def test_no_active_tool_call(self):
        h = SpanHierarchy(agent_name="test-agent")
        h.end_tool_call(success=True)
        assert h.total_tool_calls == 0


class TestSpanKind:
    def test_span_kind_values(self):
        assert SpanKind.AGENT == "agent"
        assert SpanKind.LLM_CALL == "llm_call"
        assert SpanKind.TOOL_CALL == "tool_call"
        assert SpanKind.MEMORY == "memory"
