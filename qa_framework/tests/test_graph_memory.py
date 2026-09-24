"""Tests for GraphMemoryStore."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from qa_framework.graph_memory import GraphMemoryStore


class TestGraphMemoryStore:
    def _store(self):
        return GraphMemoryStore(":memory:")

    def test_add_node(self):
        store = self._store()
        nid = store.add_node("agent", "qa-lead", metadata={"role": "testing"})
        assert nid > 0
        nodes = store.query_by_type("agent")
        assert len(nodes) == 1
        assert nodes[0]["name"] == "qa-lead"

    def test_add_duplicate_node_updates(self):
        store = self._store()
        nid1 = store.add_node("agent", "dup-agent")
        nid2 = store.add_node("agent", "dup-agent", metadata={"updated": True})
        assert nid1 == nid2
        nodes = store.query_by_type("agent")
        assert len(nodes) == 1

    def test_add_edge(self):
        store = self._store()
        a = store.add_node("agent", "agent-a")
        b = store.add_node("task", "task-1")
        eid = store.add_edge(a, b, "worked_on", confidence=0.9)
        assert eid > 0

    def test_query_related(self):
        store = self._store()
        a = store.add_node("agent", "qa-lead")
        b = store.add_node("task", "shinebringer-qa")
        c = store.add_node("file", "test_shinebringer.py")
        store.add_edge(a, b, "worked_on")
        store.add_edge(a, c, "produced")

        related = store.query_related("qa-lead")
        assert len(related) == 2

        worked = store.query_related("qa-lead", relation="worked_on")
        assert len(worked) == 1
        assert worked[0]["name"] == "shinebringer-qa"

    def test_query_by_type(self):
        store = self._store()
        store.add_node("agent", "agent-1")
        store.add_node("agent", "agent-2")
        store.add_node("task", "task-1")
        agents = store.query_by_type("agent")
        assert len(agents) == 2
        tasks = store.query_by_type("task")
        assert len(tasks) == 1

    def test_query_neighbors_single_hop(self):
        store = self._store()
        a = store.add_node("agent", "lead")
        b = store.add_node("agent", "worker-1")
        c = store.add_node("agent", "worker-2")
        store.add_edge(a, b, "delegates_to")
        store.add_edge(a, c, "delegates_to")

        neighbors = store.query_neighbors("lead", hops=1)
        names = {n["name"] for n in neighbors}
        assert "worker-1" in names
        assert "worker-2" in names

    def test_query_neighbors_multi_hop(self):
        store = self._store()
        a = store.add_node("agent", "orchestrator")
        b = store.add_node("agent", "planner")
        c = store.add_node("agent", "executor")
        store.add_edge(a, b, "delegates_to")
        store.add_edge(b, c, "delegates_to")

        neighbors = store.query_neighbors("orchestrator", hops=2)
        names = {n["name"] for n in neighbors}
        assert "executor" in names

    def test_decay_edges(self):
        store = self._store()
        a = store.add_node("agent", "old-agent")
        b = store.add_node("task", "old-task")
        store.add_edge(a, b, "worked_on")
        # decay with max_age_days=0 removes all edges created before now
        removed = store.decay_edges(max_age_days=0)
        assert removed == 1
        related = store.query_related("old-agent")
        assert len(related) == 0

    def test_stats(self):
        store = self._store()
        store.add_node("agent", "a1")
        store.add_node("agent", "a2")
        store.add_node("task", "t1")
        a1 = store.add_node("agent", "edge-source")
        t1 = store.add_node("task", "edge-target")
        store.add_edge(a1, t1, "worked_on")

        s = store.stats()
        assert s["node_count"] == 5
        assert s["edge_count"] == 1
        types = {t["entity_type"] for t in s["types"]}
        assert "agent" in types

    def test_empty_store(self):
        store = self._store()
        assert store.stats()["node_count"] == 0
        assert store.query_related("nonexistent") == []
        assert store.query_neighbors("nonexistent") == []

    def test_confidence_update(self):
        store = self._store()
        a = store.add_node("agent", "agent-x")
        b = store.add_node("task", "task-x")
        store.add_edge(a, b, "worked_on", confidence=0.5)
        store.add_edge(a, b, "worked_on", confidence=0.9)
        related = store.query_related("agent-x")
        assert len(related) == 1
        assert related[0]["confidence"] == 0.9

    def test_reputation_init(self):
        store = self._store()
        assert store.get_reputation("agent-1") == 0.5

    def test_reputation_update(self):
        store = self._store()
        store.set_reputation("agent-1", 0.7)
        assert store.get_reputation("agent-1") == 0.7

    def test_reputation_clamp_max(self):
        store = self._store()
        store.set_reputation("agent-1", 1.5)
        assert store.get_reputation("agent-1") == 1.0

    def test_reputation_clamp_min(self):
        store = self._store()
        store.set_reputation("agent-1", -0.5)
        assert store.get_reputation("agent-1") == 0.0

    def test_reputation_delta(self):
        store = self._store()
        new = store.update_reputation("agent-1", 0.1)
        assert new == pytest.approx(0.6)
        assert store.get_reputation("agent-1") == pytest.approx(0.6)
