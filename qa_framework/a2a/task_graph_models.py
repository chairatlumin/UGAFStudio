"""Task graph data models for A2A orchestration."""
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskNode(BaseModel):
    id: str
    agent: str
    prompt: str
    dependencies: List[str] = []
    status: NodeStatus = NodeStatus.PENDING
    output: Optional[str] = None
    validation_gates: List[str] = []


class TaskEdge(BaseModel):
    from_node: str
    to_node: str
    condition: Optional[str] = None


class ValidationGate(BaseModel):
    name: str
    command: str
    description: Optional[str] = None


class TaskGraph(BaseModel):
    nodes: List[TaskNode] = []
    edges: List[TaskEdge] = []
    validation_gates: List[ValidationGate] = []

    def add_node(self, node: TaskNode):
        self.nodes.append(node)

    def add_edge(self, edge: TaskEdge):
        self.edges.append(edge)

    def is_valid_dag(self) -> bool:
        """Check for cycles using DFS."""
        visited = set()
        rec_stack = set()

        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            for edge in self.edges:
                if edge.from_node == node_id:
                    if edge.to_node not in visited:
                        if has_cycle(edge.to_node):
                            return True
                    elif edge.to_node in rec_stack:
                        return True
            rec_stack.remove(node_id)
            return False

        for node in self.nodes:
            if node.id not in visited:
                if has_cycle(node.id):
                    return False
        return True
