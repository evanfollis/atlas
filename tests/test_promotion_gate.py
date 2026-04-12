"""Tests for the promotion gate logic in AutonomousRunner.evaluate_and_decide."""

import pytest
from pathlib import Path

from atlas.models.evidence import Evidence, EvidenceClass, EvidenceDirection, EvidenceQuality
from atlas.models.experiment import Experiment
from atlas.models.hypothesis import Hypothesis, HypothesisStatus
from atlas.models.session import CycleStatus, ResearchCycle
from atlas.storage.state_store import StateStore
from atlas.storage.event_store import EventStore
from atlas.storage.graph_store import GraphStore
from atlas.runner import AutonomousRunner


@pytest.fixture
def runner(tmp_path: Path) -> AutonomousRunner:
    """Create a runner with a temp directory (no network calls)."""
    r = AutonomousRunner.__new__(AutonomousRunner)
    r.base_dir = tmp_path
    r.state = StateStore(tmp_path / ".atlas")
    r.events = EventStore(tmp_path / "sessions")
    r.graph_store = GraphStore(tmp_path / "graph")
    r.methodology_log = tmp_path / "methodology.jsonl"
    return r


def _make_hypothesis(runner: AutonomousRunner, h_id: str = "h1") -> Hypothesis:
    h = Hypothesis(id=h_id, claim="test claim", rationale="r", falsification_criteria="f")
    runner._save_obj("hypotheses", h.id, h.model_dump())
    return h


def _make_cycle(runner: AutonomousRunner, h: Hypothesis) -> ResearchCycle:
    c = ResearchCycle(hypothesis_id=h.id)
    runner._save_obj("cycles", c.id, c.model_dump())
    return c


def _make_evidence(runner: AutonomousRunner, h_id: str, exp_id: str,
                   quality: EvidenceQuality, direction: EvidenceDirection,
                   ev_class: EvidenceClass = EvidenceClass.OUT_OF_SAMPLE_TEST) -> Evidence:
    ev = Evidence(
        experiment_id=exp_id,
        hypothesis_id=h_id,
        evidence_class=ev_class,
        quality=quality,
        direction=direction,
        summary="test",
    )
    runner._save_obj("evidence", ev.id, ev.model_dump())
    return ev


def test_promote_with_two_strong_oos_distinct_experiments(runner: AutonomousRunner) -> None:
    h = _make_hypothesis(runner)
    c = _make_cycle(runner, h)
    _make_evidence(runner, h.id, "exp1", EvidenceQuality.STRONG, EvidenceDirection.SUPPORTS)
    _make_evidence(runner, h.id, "exp2", EvidenceQuality.STRONG, EvidenceDirection.SUPPORTS)
    decision = runner.evaluate_and_decide(h, c)
    assert decision == "promote"


def test_no_promote_with_same_experiment(runner: AutonomousRunner) -> None:
    h = _make_hypothesis(runner)
    c = _make_cycle(runner, h)
    _make_evidence(runner, h.id, "exp1", EvidenceQuality.STRONG, EvidenceDirection.SUPPORTS)
    _make_evidence(runner, h.id, "exp1", EvidenceQuality.STRONG, EvidenceDirection.SUPPORTS)
    decision = runner.evaluate_and_decide(h, c)
    assert decision == "continue"  # only 1 distinct experiment


def test_contradiction_blocks_promotion(runner: AutonomousRunner) -> None:
    h = _make_hypothesis(runner)
    c = _make_cycle(runner, h)
    _make_evidence(runner, h.id, "exp1", EvidenceQuality.STRONG, EvidenceDirection.SUPPORTS)
    _make_evidence(runner, h.id, "exp2", EvidenceQuality.STRONG, EvidenceDirection.SUPPORTS)
    _make_evidence(runner, h.id, "exp3", EvidenceQuality.STRONG, EvidenceDirection.CONTRADICTS)
    decision = runner.evaluate_and_decide(h, c)
    assert decision == "continue"  # contradiction blocks


def test_two_contradictions_kill(runner: AutonomousRunner) -> None:
    h = _make_hypothesis(runner)
    c = _make_cycle(runner, h)
    _make_evidence(runner, h.id, "exp1", EvidenceQuality.STRONG, EvidenceDirection.CONTRADICTS)
    _make_evidence(runner, h.id, "exp2", EvidenceQuality.STRONG, EvidenceDirection.CONTRADICTS)
    decision = runner.evaluate_and_decide(h, c)
    assert decision == "kill"


def test_all_weak_after_three_attempts_kills(runner: AutonomousRunner) -> None:
    h = _make_hypothesis(runner)
    c = _make_cycle(runner, h)
    _make_evidence(runner, h.id, "exp1", EvidenceQuality.WEAK, EvidenceDirection.INCONCLUSIVE)
    _make_evidence(runner, h.id, "exp2", EvidenceQuality.WEAK, EvidenceDirection.INCONCLUSIVE)
    _make_evidence(runner, h.id, "exp3", EvidenceQuality.WEAK, EvidenceDirection.INCONCLUSIVE)
    decision = runner.evaluate_and_decide(h, c)
    assert decision == "kill"


def test_no_evidence_continues(runner: AutonomousRunner) -> None:
    h = _make_hypothesis(runner)
    c = _make_cycle(runner, h)
    decision = runner.evaluate_and_decide(h, c)
    assert decision == "continue"


def test_needs_oos_for_promotion(runner: AutonomousRunner) -> None:
    """Strong backtest-only evidence (not OOS) should not promote."""
    h = _make_hypothesis(runner)
    c = _make_cycle(runner, h)
    _make_evidence(runner, h.id, "exp1", EvidenceQuality.STRONG, EvidenceDirection.SUPPORTS,
                   ev_class=EvidenceClass.BACKTEST_RESULT)
    _make_evidence(runner, h.id, "exp2", EvidenceQuality.STRONG, EvidenceDirection.SUPPORTS,
                   ev_class=EvidenceClass.BACKTEST_RESULT)
    decision = runner.evaluate_and_decide(h, c)
    assert decision == "continue"  # no OOS evidence
