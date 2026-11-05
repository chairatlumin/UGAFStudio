"""Compaction engine that orchestrates extraction + graph operations."""

from __future__ import annotations

import re
from typing import Dict, List

from qa_framework.memory_compaction.graph_store import GraphStore
from qa_framework.memory_compaction.models import (
    CompactionConfig,
    CompactionResult,
    Edge,
    MemoryEntry,
)
from qa_framework.memory_compaction.structured_extractor import StructuredExtractor


class CompactionEngine:
    """Orchestrates extractor + graph operations to produce CompactionResult."""

    def __init__(self, config: CompactionConfig | None = None) -> None:
        self.config = config or CompactionConfig()
        self.extractor = StructuredExtractor()
        self.graph = GraphStore()

    def compact(
        self,
        session_buffer: str,
        existing_memory: List[MemoryEntry] | None = None,
    ) -> CompactionResult:
        """Compact a session buffer, preserving decisions + TODOs at full fidelity."""
        existing = existing_memory or []

        # 1. Extract structured elements
        extracted = self.extractor.extract(session_buffer)

        # 2. Build memory updates: promote existing decisions/todos, add new ones
        memory_updates: List[MemoryEntry] = []
        seen_ids: set[str] = {e.id for e in existing}

        # Preserve existing decisions and TODOs at full fidelity
        for entry in existing:
            if entry.entry_type in ("decision", "todo"):
                if entry.id not in seen_ids or entry not in existing:
                    memory_updates.append(entry)

        # Add newly extracted decisions and TODOs
        for entry in extracted.decisions:
            if entry.id not in seen_ids:
                memory_updates.append(entry)
                seen_ids.add(entry.id)

        for entry in extracted.todos:
            if entry.id not in seen_ids:
                memory_updates.append(entry)
                seen_ids.add(entry.id)

        # 3. Extract graph edges from decisions/TODOs and entities
        new_edges: List[Edge] = []
        for decision in extracted.decisions:
            content = decision.content.lower()
            # Extract task-related edges from decisions
            task_match = self._extract_task_relation(decision.content)
            if task_match:
                edge = self.graph.add_edge(
                    source=decision.content[:50],
                    target=task_match,
                    relation="task_decomposition",
                    confidence=1.0,
                )
                new_edges.append(edge)

        for entity in extracted.entities:
            content = entity.content
            if entity.metadata.get("kind") == "task_id":
                # Edge from task ID to associated agent/context
                edge = self.graph.add_edge(
                    source=content,
                    target="unknown_context",
                    relation="task_referenced",
                    confidence=0.8,
                )
                new_edges.append(edge)

        # 4. Compute compaction stats
        original_size = len(session_buffer)
        compacted_size = len(self._compact_narrative(session_buffer))
        compression_ratio = (
            (original_size - compacted_size) / original_size
            if original_size > 0
            else 0
        )

        stats: Dict[str, object] = {
            "original_size": original_size,
            "compacted_size": compacted_size,
            "compression_ratio": round(compression_ratio, 3),
            "decisions_extracted": len(extracted.decisions),
            "todos_extracted": len(extracted.todos),
            "entities_extracted": len(extracted.entities),
            "new_edges": len(new_edges),
            "memory_entries_added": len(memory_updates),
        }

        # 5. Produce compacted buffer: keep decisions/TODOs, truncate narrative
        compacted_buffer = self._compact_narrative(session_buffer)

        return CompactionResult(
            compacted_buffer=compacted_buffer,
            memory_updates=memory_updates,
            new_edges=new_edges,
            stats=stats,
        )

    def _compact_narrative(self, buffer: str) -> str:
        """Truncate narrative content while preserving decisions/TODOs."""
        lines = buffer.split("\n")
        kept: List[str] = []

        for line in lines:
            stripped = line.strip()
            # Keep decision/TODO lines at full fidelity
            if re.match(r"^(?:- \[x\]|- \[ \]|DECISION:|TODO:)", stripped):
                kept.append(line)
            # Compress other lines (truncate long exploration/narrative lines)
            elif len(line) > 120:
                kept.append(line[:120] + "...")
            else:
                kept.append(line)

        return "\n".join(kept)

    @staticmethod
    def _extract_task_relation(text: str) -> str | None:
        """Extract a task/agent relation from decision text."""
        # Look for patterns like "task: X", "agent: X", etc.
        patterns = [r"task[:\s]+(\S+)", r"agent[:\s]+(\S+)", r"(\S+)-?(\d{3,8})"]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                result: str = match.group(1)
                return result
        return None
