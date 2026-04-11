"""Persist and load the causal graph."""

import json
from pathlib import Path

from atlas.models.graph import CausalGraph


class GraphStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        self.graph_file = self.path / "causal_graph.json"

    def save(self, graph: CausalGraph) -> None:
        with open(self.graph_file, "w") as f:
            json.dump(graph.to_dict(), f, indent=2)

    def load(self) -> CausalGraph:
        if not self.graph_file.exists():
            return CausalGraph()
        with open(self.graph_file) as f:
            return CausalGraph.from_dict(json.load(f))
