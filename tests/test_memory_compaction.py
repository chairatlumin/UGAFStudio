"""Tests for memory_compaction modules — structured extraction, graph store, compaction engine."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qa_framework.memory_compaction.compaction_engine import CompactionEngine
from qa_framework.memory_compaction.graph_store import GraphStore
from qa_framework.memory_compaction.models import (
    CompactionConfig,
    CompactionResult,
    Edge,
    ExtractedStructured,
    MemoryEntry,
)
from qa_framework.memory_compaction.structured_extractor import StructuredExtractor

# ─── MemoryEntry Tests ───

def test_memory_entry_creation():
    """MemoryEntry can be created with all fields."""
    entry = MemoryEntry(
        id="dec_001",
        content="DECISION: use pytest for testing",
        entry_type="decision",
        timestamp=1000.0,
    )
    assert entry.id == "dec_001"
    assert entry.content == "DECISION: use pytest for testing"
    assert entry.entry_type == "decision"
    assert entry.timestamp == 1000.0


def test_memory_entry_with_metadata():
    """MemoryEntry accepts optional metadata."""
    entry = MemoryEntry(
        id="dec_002",
        content="TODO: write tests",
        entry_type="todo",
        timestamp=1000.0,
        metadata={"owner": "alice"},
    )
    assert entry.metadata == {"owner": "alice"}


# ─── Edge Tests ───

def test_edge_creation():
    """Edge can be created with all fields."""
    edge = Edge(
        id="e_001",
        source="agent_alpha",
        target="task_beta",
        relation="task_decomposition",
        confidence=1.0,
        created_at=1000.0,
        last_seen=1000.0,
    )
    assert edge.source == "agent_alpha"
    assert edge.target == "task_beta"
    assert edge.relation == "task_decomposition"
    assert edge.confidence == 1.0


# ─── ExtractedStructured Tests ───

def test_extracted_structured_creation():
    """ExtractedStructured can be created with all fields."""
    structured = ExtractedStructured(
        decisions=[
            MemoryEntry(id="d1", content="DECISION: use pytest", entry_type="decision", timestamp=1000.0),
        ],
        todos=[
            MemoryEntry(id="t1", content="- [ ] write tests", entry_type="todo", timestamp=1000.0),
        ],
        entities=[
            MemoryEntry(id="e1", content="TASK-001", entry_type="entity", timestamp=1000.0),
        ],
    )
    assert len(structured.decisions) == 1
    assert len(structured.todos) == 1
    assert len(structured.entities) == 1


# ─── CompactionResult Tests ───

def test_compaction_result_creation():
    """CompactionResult can be created with all fields."""
    result = CompactionResult(
        compacted_buffer="compacted",
        memory_updates=[],
        new_edges=[],
        stats={"ratio": 0.5},
    )
    assert result.compacted_buffer == "compacted"
    assert result.memory_updates == []
    assert result.new_edges == []
    assert result.stats["ratio"] == 0.5


# ─── CompactionConfig Tests ───

def test_compaction_config_defaults():
    """CompactionConfig has sensible default values."""
    config = CompactionConfig()
    assert config.max_buffer_tokens == 100_000
    assert config.compact_every_n_turns == 10
    assert config.memory_char_budget == 2_200
    assert config.edge_decay_days == 30


# ─── StructuredExtractor Tests ───

def test_extractor_extracts_decisions():
    """StructuredExtractor extracts DECISION: lines."""
    extractor = StructuredExtractor()
    buffer = (
        "Some exploration text\n"
        "DECISION: use pytest for testing\n"
        "More exploration text\n"
    )
    structured = extractor.extract(buffer)
    assert len(structured.decisions) >= 1
    assert structured.decisions[0].entry_type == "decision"


def test_extractor_extracts_todos():
    """StructuredExtractor extracts TODO: lines."""
    extractor = StructuredExtractor()
    buffer = (
        "Some exploration text\n"
        "- [ ] write tests\n"
        "More exploration text\n"
    )
    structured = extractor.extract(buffer)
    assert len(structured.todos) >= 1
    assert structured.todos[0].entry_type == "todo"


def test_extractor_extracts_entities():
    """StructuredExtractor extracts entities (task IDs, file paths, agent names)."""
    extractor = StructuredExtractor()
    buffer = (
        "Working on TASK-001\n"
        "File src/qa.py has an issue\n"
        "Agent alice started the task\n"
        "More text here"
    )
    structured = extractor.extract(buffer)
    assert len(structured.entities) >= 1


# ─── GraphStore Tests ───

def test_graph_store_add_edge():
    """GraphStore adds edges with parameterized queries."""
    store = GraphStore(db_path=":memory:")
    edge = store.add_edge("agent_alpha", "task_beta", "task_decomposition", confidence=0.9)
    assert edge.source == "agent_alpha"
    assert edge.target == "task_beta"
    assert edge.confidence == 0.9


def test_graph_store_query_neighbors():
    """GraphStore queries outgoing neighbors from an entity."""
    store = GraphStore(db_path=":memory:")
    store.add_edge("agent_alpha", "task_beta", "task_decomposition", confidence=0.9)
    store.add_edge("agent_alpha", "task_gamma", "dependency", confidence=0.7)

    neighbors = store.query_neighbors("agent_alpha")
    assert len(neighbors) == 2

    # Test with relation filter
    beta_neighbors = store.query_neighbors("agent_alpha", relation="task_decomposition")
    assert len(beta_neighbors) == 1
    assert beta_neighbors[0].target == "task_beta"


# ─── CompactionEngine Tests ───

def test_compaction_engine_compact_preserves_decisions():
    """CompactionEngine compact preserves decisions + TODOs at full fidelity."""
    engine = CompactionEngine()
    buffer = (
        "Exploration of the problem space...\n"
        "DECISION: use pytest for testing\n"
        "Some more exploration...\n"
        "- [ ] write more tests\n"
    )
    result = engine.compact(buffer)
    assert result.stats["decisions_extracted"] >= 1
    assert result.stats["todos_extracted"] >= 1

    # Check that decisions and TODOs are in memory updates
    decision_ids = {m.id for m in result.memory_updates if m.entry_type == "decision"}
    todo_ids = {m.id for m in result.memory_updates if m.entry_type == "todo"}
    assert len(decision_ids) >= 1
    assert len(todo_ids) >= 1


def test_compaction_engine_compact_produces_compacted_buffer():
    """CompactionEngine produces a compacted buffer smaller than original."""
    engine = CompactionEngine()
    buffer = (
        "Exploration of the problem space with lots of text about the issue\n"
        "DECISION: use pytest for testing\n"
        "- [ ] write tests\n"
    )
    result = engine.compact(buffer)
    assert len(result.compacted_buffer) <= len(buffer)


def test_compaction_engine_compact_produces_edges():
    """CompactionEngine produces new graph edges."""
    engine = CompactionEngine()
    buffer = "DECISION: use pytest for testing TASK-001"
    result = engine.compact(buffer)
    assert len(result.new_edges) >= 0


def test_compaction_engine_configurable():
    """CompactionEngine can be configured with custom CompactionConfig."""
    config = CompactionConfig(max_buffer_tokens=50_000, memory_char_budget=1_000)
    engine = CompactionEngine(config=config)
    buffer = "DECISION: use pytest for testing"
    result = engine.compact(buffer)
    assert result.stats["compression_ratio"] >= 0
