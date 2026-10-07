"""Tests for task graph manager."""
import pytest
from qa_framework.a2a.task_graph_manager import TaskGraphManager
from qa_framework.a2a.task_graph_models import TaskNode, TaskEdge, NodeStatus


def test_manager_creates_graph():
    manager = TaskGraphManager()
    graph = manager.create_graph("test-task")
    assert graph is not None
    assert len(graph.nodes) == 0


def test_manager_adds_node():
    manager = TaskGraphManager()
    manager.add_node(TaskNode(id="n1", agent="hermes", prompt="Plan", dependencies=[]))
    assert len(manager.graph.nodes) == 1


def test_manager_validates_dag():
    manager = TaskGraphManager()
    manager.add_node(TaskNode(id="a", agent="hermes", prompt="Plan", dependencies=[]))
    manager.add_node(TaskNode(id="b", agent="opencode", prompt="Build", dependencies=["a"]))
    manager.add_edge(TaskEdge(from_node="a", to_node="b"))
    assert manager.validate() is True


def test_manager_get_ready_nodes():
    manager = TaskGraphManager()
    manager.add_node(TaskNode(id="a", agent="hermes", prompt="Plan", dependencies=[]))
    manager.add_node(TaskNode(id="b", agent="opencode", prompt="Build", dependencies=["a"]))
    manager.add_edge(TaskEdge(from_node="a", to_node="b"))
    ready = manager.get_ready_nodes()
    assert len(ready) == 1
    assert ready[0].id == "a"


def test_manager_get_ready_nodes_after_completion():
    manager = TaskGraphManager()
    manager.add_node(TaskNode(id="a", agent="hermes", prompt="Plan", dependencies=[]))
    manager.add_node(TaskNode(id="b", agent="opencode", prompt="Build", dependencies=["a"]))
    manager.add_edge(TaskEdge(from_node="a", to_node="b"))
    manager.update_node_status("a", NodeStatus.COMPLETED)
    ready = manager.get_ready_nodes()
    assert len(ready) == 1
    assert ready[0].id == "b"


def test_manager_update_node_status():
    manager = TaskGraphManager()
    manager.add_node(TaskNode(id="a", agent="hermes", prompt="Plan", dependencies=[]))
    manager.update_node_status("a", NodeStatus.COMPLETED, output="done")
    node = manager.get_node("a")
    assert node.status == NodeStatus.COMPLETED
    assert node.output == "done"
