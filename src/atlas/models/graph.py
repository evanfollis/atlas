"""CausalGraph — directed graph of tested market claims."""

from atlas.models.hypothesis import Hypothesis
from atlas.models.primitive import ReasoningPrimitive

import networkx as nx


class CausalGraph:
    """Wrapper around networkx DiGraph for promoted and refuted claims.

    Promoted primitives remain the highest-trust positive knowledge. Refuted
    claims are lower-trust map content: they record tested absence/failure of
    an effect so Atlas can reason about what cannot co-hold without treating
    the claim as a trading-ready primitive.
    """

    def __init__(self) -> None:
        self.g = nx.DiGraph()

    def add_primitive(self, p: ReasoningPrimitive) -> None:
        self.g.add_node(
            p.id,
            node_type="primitive",
            status="promoted",
            trust="high",
            claim=p.claim,
            hypothesis_id=p.hypothesis_id,
            evidence_ids=p.evidence_ids,
            confidence=p.confidence,
            domain=p.domain,
            tags=p.tags,
        )
        for parent_id in p.causal_parents:
            if parent_id not in self.g:
                raise ValueError(f"Parent primitive {parent_id} not found in graph")
            self.g.add_edge(parent_id, p.id, relation="supports")

    def add_refuted_hypothesis(
        self,
        h: Hypothesis,
        evidence_ids: list[str],
        *,
        contradiction_count: int = 0,
    ) -> str:
        """Add or update a tested refutation/null-effect claim in the map."""
        node_id = f"refuted:{h.id}"
        confidence = min(0.95, 0.45 + 0.05 * len(evidence_ids) + 0.1 * contradiction_count)
        self.g.add_node(
            node_id,
            node_type="claim",
            status="refuted",
            trust="tested_refutation",
            claim=h.claim,
            hypothesis_id=h.id,
            evidence_ids=evidence_ids,
            contradiction_count=contradiction_count,
            confidence=confidence,
            domain=h.domain,
            tags=h.tags,
            rationale=h.rationale,
            falsification_criteria=h.falsification_criteria,
        )
        if h.parent_primitive_id and h.parent_primitive_id in self.g:
            self.g.add_edge(h.parent_primitive_id, node_id, relation="contradicts_or_limits")
        return node_id

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

    def nodes_by_status(self, status: str) -> list[str]:
        return [
            node_id
            for node_id, data in self.g.nodes(data=True)
            if self._status_for(data) == status
        ]

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, data in self.g.nodes(data=True):
            status = self._status_for(data)
            counts[status] = counts.get(status, 0) + 1
        return counts

    @staticmethod
    def _status_for(data: dict) -> str:
        # Legacy graph files predate status metadata and contained only
        # promoted primitives.
        return str(data.get("status") or "promoted")

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
            return "Empty graph — no tested claims yet."
        counts = self.status_counts()
        count_text = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
        lines = [f"Causal Graph: {self.node_count} claims ({count_text}), {self.edge_count} edges", ""]
        for node_id in nx.topological_sort(self.g):
            data = self.g.nodes[node_id]
            parents = list(self.g.predecessors(node_id))
            children = list(self.g.successors(node_id))
            indent = "  " if parents else ""
            status = self._status_for(data)
            trust = data.get("trust", "?")
            line = (
                f"{indent}[{node_id}] ({status}/{trust}) "
                f"{data.get('claim', '?')} (conf: {data.get('confidence', '?')})"
            )
            if parents:
                line += f" ← {', '.join(parents)}"
            if children:
                line += f" → {', '.join(children)}"
            lines.append(line)
        return "\n".join(lines)
