"""Regex-based extraction of decisions, TODOs, and entities from session buffers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Set

from qa_framework.memory_compaction.models import ExtractedStructured, MemoryEntry


class StructuredExtractor:
    """Extract structured elements from raw session buffer text."""

    # Decision patterns: lines starting with "- [x]" or "DECISION:"
    DECISION_PATTERN = re.compile(
        r"^(?:- \[x\]|DECISION:)[\s\S]*?$",
        re.MULTILINE,
    )

    # TODO patterns: lines starting with "- [ ]" or "TODO:"
    TODO_PATTERN = re.compile(
        r"^(?:- \[ \]|TODO:)[\s\S]*?$",
        re.MULTILINE,
    )

    # Entity patterns: file paths, agent names, task IDs
    FILE_PATH_PATTERN = re.compile(r"[/\w\-\.]+\.\w{1,5}")
    AGENT_NAME_PATTERN = re.compile(r"\b[a-z][a-z0-9_]{2,15}\b")
    TASK_ID_PATTERN = re.compile(r"\bTASK-\d{3,8}\b")

    def extract(self, session_buffer: str) -> ExtractedStructured:
        """Extract decisions, TODOs, and entities from a session buffer."""
        decisions = self._extract_entries(session_buffer, "decision")
        todos = self._extract_entries(session_buffer, "todo")
        entities = self._extract_entities(session_buffer)
        narrative_ranges = self._compute_narrative_ranges(session_buffer)

        return ExtractedStructured(
            decisions=decisions,
            todos=todos,
            entities=entities,
            narrative_ranges=narrative_ranges,
        )

    def _extract_entries(
        self, buffer: str, entry_type: str
    ) -> List[MemoryEntry]:
        """Extract typed entries (decisions or TODOs) from buffer."""
        entries: List[MemoryEntry] = []

        if entry_type == "decision":
            pattern = self.DECISION_PATTERN
            entry_keyword = "decision"
        else:
            pattern = self.TODO_PATTERN
            entry_keyword = "todo"

        for i, line in enumerate(buffer.split("\n")):
            if pattern.match(line.strip()):
                entry_id = f"{entry_keyword}_{i}"
                entries.append(
                    MemoryEntry(
                        id=entry_id,
                        content=line.strip(),
                        entry_type=entry_keyword,
                        timestamp=datetime.now(timezone.utc).timestamp(),
                    )
                )

        return entries

    def _extract_entities(self, buffer: str) -> List[MemoryEntry]:
        """Extract entity mentions from buffer."""
        entries: List[MemoryEntry] = []

        # File paths
        for match in self.FILE_PATH_PATTERN.finditer(buffer):
            content = match.group()
            if content.startswith(".") or content.startswith("/"):
                entry_id = f"entity_file_{len(entries)}"
                entries.append(
                    MemoryEntry(
                        id=entry_id,
                        content=content,
                        entry_type="entity",
                        timestamp=datetime.now(timezone.utc).timestamp(),
                        metadata={"kind": "file_path"},
                    )
                )

        # Task IDs
        for match in self.TASK_ID_PATTERN.finditer(buffer):
            content = match.group()
            entry_id = f"entity_task_{len(entries)}"
            entries.append(
                MemoryEntry(
                    id=entry_id,
                    content=content,
                    entry_type="entity",
                    timestamp=datetime.now(timezone.utc).timestamp(),
                    metadata={"kind": "task_id"},
                )
            )

        # Agent names (dedup by content)
        seen_agents: Set[str] = set()
        for match in self.AGENT_NAME_PATTERN.finditer(buffer):
            content = match.group()
            if content in seen_agents:
                continue
            # Skip common words
            if content.lower() in {"the", "and", "for", "with", "from", "that", "this", "the"}:
                continue
            seen_agents.add(content)
            entry_id = f"entity_agent_{len(entries)}"
            entries.append(
                MemoryEntry(
                    id=entry_id,
                    content=content,
                    entry_type="entity",
                    timestamp=datetime.now(timezone.utc).timestamp(),
                    metadata={"kind": "agent_name"},
                )
            )

        return entries

    def _compute_narrative_ranges(self, buffer: str) -> List[tuple[int, int]]:
        """Compute character ranges of narrative segments (non-structured content)."""
        ranges: List[tuple[int, int]] = []
        lines = buffer.split("\n")
        in_structured = False
        start = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            is_structured = bool(
                re.match(r"^(?:- \[x\]|- \[ \]|DECISION:|TODO:)", stripped)
            )
            if is_structured and not in_structured:
                start = sum(len(line) + 1 for line in lines[:i])
                in_structured = True
            elif not is_structured and in_structured:
                end = sum(len(line) + 1 for line in lines[:i])
                ranges.append((start, end))
                in_structured = False

        if in_structured:
            end = len(buffer)
            ranges.append((start, end))

        return ranges
