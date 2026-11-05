"""Data models for memory compaction and harness evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MemoryEntry:
    """A single memory entry from a session buffer."""
    id: str
    content: str
    entry_type: str  # "decision", "todo", "entity", "narrative"
    timestamp: float
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class Edge:
    """A graph edge connecting two entities."""
    id: str
    source: str
    target: str
    relation: str
    confidence: float
    created_at: float
    last_seen: float


@dataclass
class ExtractedStructured:
    """Structured extraction from a session buffer."""
    decisions: List[MemoryEntry]
    todos: List[MemoryEntry]
    entities: List[MemoryEntry]
    narrative_ranges: List[tuple[int, int]] = field(default_factory=list)


@dataclass
class CompactionResult:
    """Result of compaction operation."""
    compacted_buffer: str
    memory_updates: List[MemoryEntry]
    new_edges: List[Edge]
    stats: Dict[str, object] = field(default_factory=dict)


@dataclass
class CompactionConfig:
    """Configuration for memory compaction."""
    max_buffer_tokens: int = 100_000
    compact_every_n_turns: int = 10
    memory_char_budget: int = 2_200
    edge_decay_days: int = 30
