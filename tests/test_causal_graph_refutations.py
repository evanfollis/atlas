"""Tests for refuted/null-effect claims in the causal graph."""

from pathlib import Path

from atlas.generation.hypotheses import from_graph_gaps
from atlas.graph_backfill import backfill_falsified_claims
from atlas.models.evidence import Evidence, EvidenceClass, EvidenceDirection, EvidenceQuality
from atlas.models.graph import CausalGraph
from atlas.models.hypothesis import Hypothesis, HypothesisStatus
from atlas.models.session import ResearchCycle
from atlas.runner import AutonomousRunner
from atlas.storage.event_store import EventStore
from atlas.storage.graph_store import GraphStore
from atlas.storage.state_store import StateStore


def _falsified_hypothesis(h_id: str = "h-refuted") -> Hypothesis:
    return Hypothesis(
        id=h_id,
        claim="BTC/USDT 1h lag-1 momentum predicts positive OOS returns",
        rationale="prior signal scan",
        falsification_criteria="OOS Sharpe is not significantly above zero",
        tags=["btc_usdt", "1h", "momentum"],
        status=HypothesisStatus.FALSIFIED,
    )


def _contradictory_evidence(h_id: str, exp_id: str = "exp-1") -> Evidence:
    return Evidence(
        id=f"ev-{exp_id}",
        experiment_id=exp_id,
        hypothesis_id=h_id,
        evidence_class=EvidenceClass.OUT_OF_SAMPLE_TEST,
        quality=EvidenceQuality.STRONG,
        direction=EvidenceDirection.CONTRADICTS,
        summary="negative OOS Sharpe after fees",
    )


def test_refuted_hypothesis_is_graph_content_but_not_promoted() -> None:
    graph = CausalGraph()
    h = _falsified_hypothesis()

    node_id = graph.add_refuted_hypothesis(h, ["ev-1"], contradiction_count=1)

    assert node_id == f"refuted:{h.id}"
    assert graph.status_counts() == {"refuted": 1}
    assert graph.nodes_by_status("promoted") == []
    assert graph.get_primitive_data(node_id)["trust"] == "tested_refutation"
    assert "refuted/tested_refutation" in graph.display()


def test_backfill_falsified_claims_creates_refuted_nodes(tmp_path: Path) -> None:
    state = StateStore(tmp_path / ".atlas")
    graph_store = GraphStore(tmp_path / "graph")
    h = _falsified_hypothesis()
    ev = _contradictory_evidence(h.id)
    state.save("hypotheses", h.id, h.model_dump())
    state.save("evidence", ev.id, ev.model_dump())

    stats = backfill_falsified_claims(state, graph_store)
    graph = graph_store.load()

    assert stats["added"] == 1
    assert stats["refuted_nodes"] == 1
    assert graph.node_count == 1
    assert graph.status_counts()["refuted"] == 1


def test_graph_gaps_generate_followup_from_refuted_claim() -> None:
    graph = CausalGraph()
    h = _falsified_hypothesis()
    graph.add_refuted_hypothesis(h, ["ev-1"], contradiction_count=1)

    gaps = from_graph_gaps(graph)

    assert len(gaps) == 1
    assert "unmodeled market regime or confounder" in gaps[0].claim
    assert "refuted_claim" in gaps[0].tags
    assert gaps[0].parent_primitive_id == f"refuted:{h.id}"


def test_runner_kill_adds_refuted_node(tmp_path: Path) -> None:
    r = AutonomousRunner.__new__(AutonomousRunner)
    r.base_dir = tmp_path
    r.state = StateStore(tmp_path / ".atlas")
    r.events = EventStore(tmp_path / "sessions")
    r.graph_store = GraphStore(tmp_path / "graph")
    r.methodology_log = tmp_path / "methodology.jsonl"

    h = Hypothesis(
        id="h-kill",
        claim="ETH/USDT 1h volume spikes predict larger positive returns",
        rationale="prior signal scan",
        falsification_criteria="OOS returns do not differ from baseline",
        tags=["eth_usdt", "1h", "volume"],
    )
    r._save_obj("hypotheses", h.id, h.model_dump())
    cycle = ResearchCycle(hypothesis_id=h.id)
    r._save_obj("cycles", cycle.id, cycle.model_dump())
    ev1 = _contradictory_evidence(h.id, "exp-1")
    ev2 = _contradictory_evidence(h.id, "exp-2")
    r._save_obj("evidence", ev1.id, ev1.model_dump())
    r._save_obj("evidence", ev2.id, ev2.model_dump())

    decision = r.evaluate_and_decide(h, cycle)
    graph = r.graph_store.load()

    assert decision == "kill"
    assert graph.status_counts() == {"refuted": 1}
    assert graph.nodes_by_status("promoted") == []
