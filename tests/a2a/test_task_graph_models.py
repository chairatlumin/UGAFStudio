"""Tests for task graph data models."""
import pytest
from qa_framework.a2a.task_graph_models import TaskNode, TaskEdge, TaskGraph, ValidationGate, NodeStatus


def test_task_node_creation():
    node = TaskNode(id="node1", agent="opencode", prompt="Write code", dependencies=[])
    assert node.id == "node1"
    assert node.agent == "opencode"
    assert node.status == NodeStatus.PENDING


def test_task_node_with_dependencies():
    node = TaskNode(id="node2", agent="hermes", prompt="Review", dependencies=["node1"])
    assert node.dependencies == ["node1"]


def test_task_graph_dag():
    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="hermes", prompt="Plan", dependencies=[]))
    graph.add_node(TaskNode(id="b", agent="opencode", prompt="Build", dependencies=["a"]))
    graph.add_edge(TaskEdge(from_node="a", to_node="b"))
    assert graph.is_valid_dag() is True


def test_task_graph_cycle_detection():
    graph = TaskGraph()
    graph.add_node(TaskNode(id="a", agent="hermes", prompt="A", dependencies=["b"]))
    graph.add_node(TaskNode(id="b", agent="opencode", prompt="B", dependencies=["a"]))
    graph.add_edge(TaskEdge(from_node="a", to_node="b"))
    graph.add_edge(TaskEdge(from_node="b", to_node="a"))
    assert graph.is_valid_dag() is False


def test_validation_gate():
    gate = ValidationGate(name="syntax_check", command="python -m py_compile {output}")
    assert gate.name == "syntax_check"
    assert "{output}" in gate.command


def test_task_edge_with_condition():
    edge = TaskEdge(from_node="a", to_node="b", condition="success")
    assert edge.condition == "success"
