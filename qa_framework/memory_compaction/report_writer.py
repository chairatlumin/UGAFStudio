"""Markdown compaction report writer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from qa_framework.memory_compaction.models import CompactionResult


def write_compaction_report(result: CompactionResult, path: Path) -> None:
    """Write a markdown compaction report to the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)

    stats = result.stats
    lines = [
        "# Memory Compaction Report",
        "",
        "## Summary",
        f"- **Original buffer size**: {stats['original_size']} characters",
        f"- **Compacted buffer size**: {stats['compacted_size']} characters",
        f"- **Compression ratio**: {stats['compression_ratio']!r}",
        f"- **Decisions extracted**: {stats['decisions_extracted']}",
        f"- **TODOs extracted**: {stats['todos_extracted']}",
        f"- **Entities extracted**: {stats['entities_extracted']}",
        f"- **New graph edges**: {stats['new_edges']}",
        f"- **Memory entries added**: {stats['memory_entries_added']}",
        "",
        "## Decisions",
    ]

    for decision in result.memory_updates:
        if decision.entry_type == "decision":
            lines.append(f"- [x] {decision.content}")

    lines.extend([
        "",
        "## TODOs",
    ])

    for entry in result.memory_updates:
        if entry.entry_type == "todo":
            lines.append(f"- [ ] {entry.content}")

    lines.extend([
        "",
        "## New Graph Edges",
    ])

    for edge in result.new_edges:
        lines.append(
            f"- **{edge.source} -> {edge.target}** "
            f"({edge.relation}, conf={edge.confidence:.2f})"
        )

    lines.extend([
        "",
        "## Memory Updates",
    ])

    for entry in result.memory_updates:
        lines.append(f"- **[{entry.entry_type}]** {entry.content[:80]}...")

    lines.append("")
    lines.append(f"*Report generated: {datetime.now().isoformat()}*")

    path.write_text("\n".join(lines), encoding="utf-8")
