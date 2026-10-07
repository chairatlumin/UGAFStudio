"""Task graph manager for A2A orchestration."""
from typing import Optional, List
from .task_graph_models import TaskGraph, TaskNode, TaskEdge, ValidationGate, NodeStatus


class TaskGraphManager:
    def __init__(self):
        self.graph = TaskGraph()

    def create_graph(self, task_id: str) -> TaskGraph:
        self.graph = TaskGraph()
        return self.graph

    def add_node(self, node: TaskNode):
        self.graph.add_node(node)

    def add_edge(self, edge: TaskEdge):
        self.graph.add_edge(edge)

    def add_validation_gate(self, gate: ValidationGate):
        self.graph.validation_gates.append(gate)

    def validate(self) -> bool:
        return self.graph.is_valid_dag()

    def get_ready_nodes(self) -> List[TaskNode]:
        """Get nodes with all dependencies completed."""
        completed = {n.id for n in self.graph.nodes if n.status == NodeStatus.COMPLETED}
        ready = []
        for node in self.graph.nodes:
            if node.status == NodeStatus.PENDING and all(dep in completed for dep in node.dependencies):
                ready.append(node)
        return ready

    def get_node(self, node_id: str) -> Optional[TaskNode]:
        for node in self.graph.nodes:
            if node.id == node_id:
                return node
        return None

    def update_node_status(self, node_id: str, status: NodeStatus, output: Optional[str] = None):
        node = self.get_node(node_id)
        if node:
            node.status = status
            if output is not None:
                node.output = output
