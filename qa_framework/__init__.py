"""UGAFStudio QA Framework — Steam gameplay QA with vision-based autoplay."""

from qa_framework.telemetry import BudgetEnforcer, SpanHierarchy, SpanKind, TelemetryProvider
from qa_framework.sandbox import ExecutionResult, SandboxAuditLog, SandboxedExecutor
from qa_framework.a2a_bridge import (
    A2AArtifact,
    A2AEvent,
    A2AMessage,
    A2AProtocolBridge,
    A2ATask,
    A2ATaskStatus,
)
from qa_framework.graph_memory import GraphMemoryStore
from qa_framework.consensus_validator import (
    Challenge,
    ConsensusResult,
    ConsensusValidator,
    Proposal,
    QAOutcome,
    QAResult,
    VoteTally,
)

__all__ = [
    # Telemetry
    "BudgetEnforcer",
    "SpanHierarchy",
    "SpanKind",
    "TelemetryProvider",
    # Sandbox
    "ExecutionResult",
    "SandboxAuditLog",
    "SandboxedExecutor",
    # A2A Bridge
    "A2AArtifact",
    "A2AEvent",
    "A2AMessage",
    "A2AProtocolBridge",
    "A2ATask",
    "A2ATaskStatus",
    # Graph Memory
    "GraphMemoryStore",
    # Consensus Validator
    "Challenge",
    "ConsensusResult",
    "ConsensusValidator",
    "Proposal",
    "QAOutcome",
    "QAResult",
    "VoteTally",
]
