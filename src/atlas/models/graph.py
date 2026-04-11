"""CausalGraph — directed graph of reasoning primitives."""

from atlas.models.primitive import ReasoningPrimitive

import networkx as nx


class CausalGraph:
    """Wrapper around networkx DiGraph for reasoning primitives."""

    def __init__(self) -> None:
        self.g = nx.DiGraph()

    def add_primitive(self, p: ReasoningPrimitive) -> None:
        self.g.add_node(p.id, claim=p.claim, confidence=p.confidence, tags=p.tags)
        for parent_id in p.causal_parents:
            if parent_id not in self.g:
                raise ValueError(f"Parent primitive {parent_id} not found in graph")
            self.g.add_edge(parent_id, p.id)

    def get_primitive_data(self, primitive_id: str) -> dict | None:
        if primitive_id in self.g:
            return dict(self.g.nodes[primitive_id])
        return None

    def roots(self) -> list[str]:
        return [n for n in self.g.nodes if self.g.in_degree(n) == 0]

    def descendants(self, primitive_id: str) -> set[str]:
        return nx.descendants(self.g, primitive_id)

    def ancestors(self, primitive_id: str) -> set[str]:
        return nx.ancestors(self.g, primitive_id)

    @property
    def node_count(self) -> int:
        return self.g.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.g.number_of_edges()

    def to_dict(self) -> dict:
        return nx.node_link_data(self.g)

    @classmethod
    def from_dict(cls, data: dict) -> "CausalGraph":
        graph = cls()
        graph.g = nx.node_link_graph(data)
        return graph

    def display(self) -> str:
        if self.node_count == 0:
            return "Empty graph — no reasoning primitives yet."
        lines = [f"Causal Graph: {self.node_count} primitives, {self.edge_count} edges", ""]
        for node_id in nx.topological_sort(self.g):
            data = self.g.nodes[node_id]
            parents = list(self.g.predecessors(node_id))
            children = list(self.g.successors(node_id))
            indent = "  " if parents else ""
            line = f"{indent}[{node_id}] {data.get('claim', '?')} (conf: {data.get('confidence', '?')})"
            if parents:
                line += f" ← {', '.join(parents)}"
            if children:
                line += f" → {', '.join(children)}"
            lines.append(line)
        return "\n".join(lines)
