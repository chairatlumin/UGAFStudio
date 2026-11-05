"""Memory compaction and harness evaluation for Hermes cron auto-researcher."""

from qa_framework.memory_compaction.compaction_engine import CompactionEngine
from qa_framework.memory_compaction.config import CompactionConfig
from qa_framework.memory_compaction.graph_store import GraphStore
from qa_framework.memory_compaction.models import (
    CompactionResult,
    Edge,
    ExtractedStructured,
    MemoryEntry,
)
from qa_framework.memory_compaction.report_writer import write_compaction_report
from qa_framework.memory_compaction.structured_extractor import StructuredExtractor

__all__ = [
    "CompactionConfig",
    "CompactionEngine",
    "CompactionResult",
    "Edge",
    "ExtractedStructured",
    "GraphStore",
    "MemoryEntry",
    "StructuredExtractor",
    "write_compaction_report",
]
