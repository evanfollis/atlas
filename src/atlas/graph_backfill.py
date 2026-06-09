"""Utilities for projecting tested hypotheses into the causal map."""

from atlas.models.evidence import Evidence, EvidenceDirection, EvidenceQuality
from atlas.models.hypothesis import Hypothesis, HypothesisStatus
from atlas.storage.graph_store import GraphStore
from atlas.storage.state_store import StateStore


def backfill_falsified_claims(state: StateStore, graph_store: GraphStore) -> dict[str, int]:
    """Write existing falsified hypotheses into the causal graph as refuted claims."""
    graph = graph_store.load()
    evidence_by_hypothesis: dict[str, list[Evidence]] = {}
    for raw in state.list_all("evidence"):
        evidence = Evidence.model_validate(raw)
        evidence_by_hypothesis.setdefault(evidence.hypothesis_id, []).append(evidence)

    added = 0
    updated = 0
    skipped = 0
    for raw in state.list_all("hypotheses"):
        hypothesis = Hypothesis.model_validate(raw)
        if hypothesis.status != HypothesisStatus.FALSIFIED:
            skipped += 1
            continue

        evidence = evidence_by_hypothesis.get(hypothesis.id, [])
        evidence_ids = [e.id for e in evidence]
        contradiction_count = sum(
            1
            for e in evidence
            if e.quality == EvidenceQuality.STRONG
            and e.direction == EvidenceDirection.CONTRADICTS
        )
        node_id = f"refuted:{hypothesis.id}"
        existed = node_id in graph.g
        graph.add_refuted_hypothesis(
            hypothesis,
            evidence_ids,
            contradiction_count=contradiction_count,
        )
        if existed:
            updated += 1
        else:
            added += 1

    graph_store.save(graph)
    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "graph_nodes": graph.node_count,
        "graph_edges": graph.edge_count,
        "refuted_nodes": graph.status_counts().get("refuted", 0),
    }
