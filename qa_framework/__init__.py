"""UGAFStudio QA Framework — Steam gameplay QA with vision-based autoplay."""

from qa_framework.a2a_bridge import (
    A2AArtifact,
    A2AEvent,
    A2AMessage,
    A2AProtocolBridge,
    A2ATask,
    A2ATaskStatus,
)
from qa_framework.a2a_spec_compliance import AgentCard, TaskLifecycle
from qa_framework.adversarial_vision import AdversarialVisionGuard, VisionTrustScore
from qa_framework.circuit_breaker import CircuitBreaker
from qa_framework.consensus_validator import (
    Challenge,
    ConsensusResult,
    ConsensusValidator,
    Proposal,
    QAOutcome,
    QAResult,
    VoteTally,
)
from qa_framework.fleet_monitor import FleetMonitor, FleetRecorder
from qa_framework.graph_memory import GraphMemoryStore
from qa_framework.intent_scanner import (
    Finding,
    IntentScanner,
    ScanResult,
)
from qa_framework.memory_compactor import MemoryCompactor, MemoryTier
from qa_framework.qa_evaluator import QAEvaluator, QAEvaluatorVerdict
from qa_framework.reliability_tracker import DispatchOutcome, ReliabilityMetrics, ReliabilityTracker
from qa_framework.pbft_consensus import (
    PBFTMessage,
    PBFTNetwork,
    PBFTNode,
    PBFTPhase,
    PBFTResult,
    QuorumCertificate,
)
from qa_framework.sandbox import ExecutionResult, SandboxAuditLog, SandboxedExecutor
from qa_framework.team_mode_dispatcher import (
    StageResult,
    TeamModeDispatcher,
    TeamResult,
    TeamTask,
)
from qa_framework.telemetry import BudgetEnforcer, SpanHierarchy, SpanKind, TelemetryProvider
from qa_framework.tool_result_validator import ToolResultValidator, ValidationResult
from qa_framework.workspace_locker import WorkspaceLocker

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
    # Intent Scanner
    "Finding",
    "IntentScanner",
    "ScanResult",
    # Team Mode Dispatcher
    "StageResult",
    "TeamModeDispatcher",
    "TeamResult",
    "TeamTask",
    # PBFT Consensus
    "PBFTNetwork",
    "PBFTNode",
    "PBFTResult",
    "PBFTMessage",
    "PBFTPhase",
    "QuorumCertificate",
    # A2A Spec Compliance
    "AgentCard",
    "TaskLifecycle",
    # Resilience Components
    "CircuitBreaker",
    "WorkspaceLocker",
    "AdversarialVisionGuard",
    "VisionTrustScore",
    "ReliabilityTracker",
    "ReliabilityMetrics",
    "DispatchOutcome",
    "ToolResultValidator",
    "ValidationResult",
    "MemoryCompactor",
    "MemoryTier",
    # Fleet Monitor
    "FleetMonitor",
    "FleetRecorder",
    # QA Evaluator
    "QAEvaluator",
    "QAEvaluatorVerdict",
]
