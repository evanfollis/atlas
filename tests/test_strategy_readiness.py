"""Tests for strategy-readiness predicate, S3-P2 escalation gate, and the
`atlas strategy readiness` CLI command."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from atlas.cli import cli
from atlas.models.evidence import (
    Evidence, EvidenceClass, EvidenceDirection, EvidenceQuality,
)
from atlas.runner import (
    AutonomousRunner,
    FROZEN_LOOP_ESCALATION_AFTER,
    evaluate_promotion_gate,
)
from atlas.storage.event_store import EventStore
from atlas.storage.graph_store import GraphStore
from atlas.storage.state_store import StateStore


def _ev(experiment_id: str, **overrides) -> Evidence:
    base = dict(
        hypothesis_id="h1",
        experiment_id=experiment_id,
        evidence_class=EvidenceClass.OUT_OF_SAMPLE_TEST,
        quality=EvidenceQuality.STRONG,
        direction=EvidenceDirection.SUPPORTS,
        summary="s",
    )
    base.update(overrides)
    return Evidence(**base)


# --------------------------------------------------------------------------
# evaluate_promotion_gate predicate
# --------------------------------------------------------------------------


def test_promotable_when_two_distinct_oos_strong_supports():
    ev = [_ev("e1"), _ev("e2")]
    gate = evaluate_promotion_gate(ev)
    assert gate["promotable"] is True
    assert gate["distinct_experiments"] == 2
    assert len(gate["oos_support"]) == 2


def test_not_promotable_when_one_strong_contradiction_present():
    ev = [_ev("e1"), _ev("e2"),
          _ev("e3", direction=EvidenceDirection.CONTRADICTS)]
    gate = evaluate_promotion_gate(ev)
    assert gate["promotable"] is False
    assert len(gate["strong_contradict"]) == 1


def test_not_promotable_when_no_oos_support():
    ev = [
        _ev("e1", evidence_class=EvidenceClass.BACKTEST_RESULT),
        _ev("e2", evidence_class=EvidenceClass.BACKTEST_RESULT),
    ]
    gate = evaluate_promotion_gate(ev)
    assert gate["promotable"] is False
    assert gate["distinct_experiments"] == 2
    assert len(gate["oos_support"]) == 0


def test_not_promotable_when_only_one_distinct_experiment():
    ev = [_ev("e1"), _ev("e1")]
    gate = evaluate_promotion_gate(ev)
    assert gate["promotable"] is False
    assert gate["distinct_experiments"] == 1


# --------------------------------------------------------------------------
# Frozen-loop escalation gate
# --------------------------------------------------------------------------


@pytest.fixture
def runner_with_telemetry(tmp_path: Path, monkeypatch) -> AutonomousRunner:
    r = AutonomousRunner.__new__(AutonomousRunner)
    r.base_dir = tmp_path
    r.state = StateStore(tmp_path / ".atlas")
    r.events = EventStore(tmp_path / "sessions")
    r.graph_store = GraphStore(tmp_path / "graph")
    r.methodology_log = tmp_path / "methodology.jsonl"
    # Redirect telemetry + handoffs to tmp so this test stays hermetic.
    telem = tmp_path / "telemetry" / "events.jsonl"
    telem.parent.mkdir()
    monkeypatch.setattr(AutonomousRunner, "TELEMETRY_PATH", telem)
    monkeypatch.setattr(AutonomousRunner, "HANDOFF_DIR", tmp_path / "handoff")
    return r


def _simulate_cycles(runner: AutonomousRunner, decisions_list: list[dict]) -> None:
    """Call _update_streak_counter once per entry to simulate cycle outcomes.
    Each entry is a decisions_by_kind dict (e.g. {"continue": 5} or {})."""
    for decisions in decisions_list:
        runner._update_streak_counter(decisions)


def _read_runner_event_types(runner: AutonomousRunner) -> list[str]:
    return [e["eventType"] for e in _all_runner_events(runner)]


def _all_runner_events(runner: AutonomousRunner) -> list[dict]:
    out: list[dict] = []
    if not runner.TELEMETRY_PATH.exists():
        return out
    with open(runner.TELEMETRY_PATH) as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("source") == "atlas.runner":
                out.append(e)
    return out


def test_escalation_fires_after_threshold(runner_with_telemetry):
    r = runner_with_telemetry
    _simulate_cycles(r, [{"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()
    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 1
    handoffs = list(r.HANDOFF_DIR.glob("URGENT-atlas-frozen-loop-*.md"))
    assert len(handoffs) == 1


def test_escalation_idempotent_on_same_streak(runner_with_telemetry):
    r = runner_with_telemetry
    _simulate_cycles(r, [{"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()
    r._maybe_escalate_frozen_loop()  # second call must not re-emit
    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 1
    # Handoff dedup also: still exactly one URGENT file.
    handoffs = list(r.HANDOFF_DIR.glob("URGENT-atlas-frozen-loop-*.md"))
    assert len(handoffs) == 1


def test_escalation_idempotent_when_streak_grows_past_threshold(runner_with_telemetry):
    """Regression for the 2026-04-26 02:37 false-re-emit:
    once the all-continue streak passes the threshold, additional
    same-streak cycles must NOT trigger a second cycle.escalated."""
    r = runner_with_telemetry
    _simulate_cycles(r, [{"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()  # streak hits threshold → 1 emission

    # Streak grows past threshold — no break, no re-emit.
    _simulate_cycles(r, [{"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()  # same streak — must NOT re-emit

    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 1, (
        "gate re-fired on a streak that never broke"
    )
    handoffs = list(r.HANDOFF_DIR.glob("URGENT-atlas-frozen-loop-*.md"))
    assert len(handoffs) == 1


def test_state_file_corruption_falls_back_to_empty(runner_with_telemetry, tmp_path):
    """Corrupt / wrong-shape state file must not poison the gate —
    `_load_escalation_state` returns {} for any parse failure."""
    r = runner_with_telemetry
    state_path = r._escalation_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    state_path.write_text("not json")
    assert r._load_escalation_state() == {}

    state_path.write_text(json.dumps([1, 2, 3]))
    assert r._load_escalation_state() == {}

    state_path.write_text(json.dumps({"consecutive_empty_count": "not-an-int"}))
    assert r._load_escalation_state() == {}

    state_path.write_text(json.dumps({"consecutive_empty_count": None}))
    assert r._load_escalation_state() == {}

    state_path.write_text(json.dumps({"consecutive_empty_count": 5}))
    assert r._load_escalation_state() == {"consecutive_empty_count": 5}


def test_dedup_suppresses_after_midnight_rotation_when_no_break_visible(runner_with_telemetry):
    """Regression for the 2026-04-28 rotation-induced false-positive:
    once a streak is marked emitted, additional all-continue cycles must
    not re-trigger the gate even if the telemetry log rotates and the
    prior emission event disappears. The persistent emitted_for_current_streak
    flag is the source of truth — the gate never reads events.jsonl."""
    r = runner_with_telemetry
    # Build a 3-cycle streak and fire the gate.
    _simulate_cycles(r, [{"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()  # fires; emitted_for_current_streak → True

    # Simulate midnight rotation: wipe events.jsonl. Counter-based gate is unaffected.
    r.TELEMETRY_PATH.write_text("")

    # Three more all-continue cycles — same streak, counter keeps incrementing.
    _simulate_cycles(r, [{"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()  # same streak — must NOT re-emit

    # No cycle.escalated in the post-wipe file (second call suppressed correctly).
    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 0


def test_visible_kill_after_old_emission_triggers_re_emit(runner_with_telemetry):
    """A kill cycle resets the streak counter; a new all-continue streak
    after the kill must trigger a second escalation."""
    r = runner_with_telemetry
    # First streak fires the gate.
    _simulate_cycles(r, [{"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()
    assert _read_runner_event_types(r).count("cycle.escalated") == 1

    # Kill breaks the streak, then a new 3-cycle streak forms.
    _simulate_cycles(r, [{"kill": 5}, {"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()
    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 2


def test_escalation_idempotent_across_telemetry_rotation(runner_with_telemetry):
    """Regression for the 2026-04-27 02:36 false-re-emit:
    once cycle.escalated has been emitted for a streak, a midnight telemetry
    rotation that wipes the cycle.escalated event from events.jsonl must
    NOT cause the gate to re-emit. State persists in
    .atlas/escalation_state.json, not in the rotated telemetry."""
    r = runner_with_telemetry
    _simulate_cycles(r, [{"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()  # 1st emission, state file written

    # Simulate telemetry rotation: wipe events.jsonl.
    r.TELEMETRY_PATH.write_text("")

    # 3 more all-continue cycles — same streak.
    _simulate_cycles(r, [{"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()  # same logical streak — must NOT re-emit

    # No cycle.escalated in the post-rotation file.
    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 0, (
        "cycle.escalated event in *post-rotation* file means the gate re-fired "
        "after rotation hid the prior emission"
    )
    handoffs = list(r.HANDOFF_DIR.glob("URGENT-atlas-frozen-loop-*.md"))
    assert len(handoffs) == 1


def test_escalation_re_fires_after_streak_breaks_then_reforms(runner_with_telemetry):
    """Sanity check: a kill cycle resets the counter; a new 3-cycle
    all-continue run AFTER that kill must trigger a SECOND escalation."""
    r = runner_with_telemetry
    _simulate_cycles(r, [{"continue": 5}, {"continue": 5}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()  # 1st emission

    # Kill breaks the streak, then a new streak forms.
    _simulate_cycles(r, [
        {"kill": 5},
        {"continue": 5}, {"continue": 5}, {"continue": 5},
    ])
    r._maybe_escalate_frozen_loop()  # NEW streak → SHOULD re-emit

    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 2


def test_escalation_skipped_when_kill_within_window(runner_with_telemetry):
    r = runner_with_telemetry
    _simulate_cycles(r, [
        {"continue": 5},
        {"kill": 1, "continue": 4},  # mixed: decisive → resets counter
        {"continue": 5},
    ])
    r._maybe_escalate_frozen_loop()
    types = _read_runner_event_types(r)
    assert "cycle.escalated" not in types


def test_empty_cycles_count_as_stuck(runner_with_telemetry):
    """Regression for the 2026-04-30 14:18Z 'No hypotheses generated' freeze:
    14+ empty cycles ran without the gate firing because the previous
    semantics SKIPPED vacuous cycles (treating them as neither stuck nor
    productive). They are stuck — the loop is producing no falsifying
    evidence and no decisions. Three consecutive empty cycles must trigger
    the gate."""
    r = runner_with_telemetry
    _simulate_cycles(r, [{}, {}, {}])  # empty cycles
    r._maybe_escalate_frozen_loop()
    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 1


def test_mixed_empty_and_all_continue_cycles_form_streak(runner_with_telemetry):
    """A streak of stuck cycles can mix empty + all-continue; both forms
    are 'no kill/promote/pivot was produced' and must be treated as one
    contiguous streak."""
    r = runner_with_telemetry
    _simulate_cycles(r, [{"continue": 5}, {}, {"continue": 5}])
    r._maybe_escalate_frozen_loop()
    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 1


def test_kill_breaks_a_streak_of_empty_cycles(runner_with_telemetry):
    """A real kill must still reset a streak even if surrounded by empty cycles."""
    r = runner_with_telemetry
    _simulate_cycles(r, [{}, {"kill": 5}, {}, {}])
    r._maybe_escalate_frozen_loop()
    types = _read_runner_event_types(r)
    # Streak (after kill) = 2 empties → below threshold of 3
    assert types.count("cycle.escalated") == 0


def test_escalation_threshold_constant_matches_workspace_rule():
    """Workspace CLAUDE.md S3-P2 sets the threshold to 3 consecutive
    same-reason skips. Drift here would silently weaken the gate."""
    assert FROZEN_LOOP_ESCALATION_AFTER == 3


def test_update_streak_counter_increments_on_empty(runner_with_telemetry):
    r = runner_with_telemetry
    r._update_streak_counter({})
    assert r._load_escalation_state().get("consecutive_empty_count") == 1
    r._update_streak_counter({})
    assert r._load_escalation_state().get("consecutive_empty_count") == 2


def test_update_streak_counter_increments_on_all_continue(runner_with_telemetry):
    r = runner_with_telemetry
    r._update_streak_counter({"continue": 5})
    r._update_streak_counter({"continue": 3})
    assert r._load_escalation_state().get("consecutive_empty_count") == 2


def test_update_streak_counter_resets_on_kill(runner_with_telemetry):
    r = runner_with_telemetry
    r._update_streak_counter({})
    r._update_streak_counter({})
    r._update_streak_counter({})
    assert r._load_escalation_state().get("consecutive_empty_count") == 3
    r._update_streak_counter({"kill": 2})
    state = r._load_escalation_state()
    assert state.get("consecutive_empty_count") == 0
    assert state.get("emitted_for_current_streak") is False


def test_update_streak_counter_resets_on_promote(runner_with_telemetry):
    r = runner_with_telemetry
    r._update_streak_counter({"continue": 5})
    r._update_streak_counter({"promote": 1, "continue": 4})
    state = r._load_escalation_state()
    assert state.get("consecutive_empty_count") == 0
    assert state.get("emitted_for_current_streak") is False


def test_rotation_proof_counter_persists_across_events_wipe(runner_with_telemetry):
    """Regression for the 2026-04-27/28 rotation bugs (now eliminated):
    the counter-based gate must not depend on events.jsonl at all. Wiping
    events.jsonl while a streak is in progress must not affect the counter
    or the emitted flag.

    Scenario: 3 empties → gate fires → wipe events.jsonl → 0 new cycles →
    gate stays silent (emitted_for_current_streak=True in state file)."""
    r = runner_with_telemetry
    _simulate_cycles(r, [{}, {}, {}])
    r._maybe_escalate_frozen_loop()  # fires

    state = r._load_escalation_state()
    assert state.get("emitted_for_current_streak") is True
    assert state.get("consecutive_empty_count", 0) >= 3

    # Wipe events.jsonl (simulate midnight rotation).
    r.TELEMETRY_PATH.write_text("")

    # Gate must not re-fire.
    r._maybe_escalate_frozen_loop()
    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 0


# --------------------------------------------------------------------------
# atlas strategy readiness CLI
# --------------------------------------------------------------------------


def test_cli_classification_is_research_only_when_no_primitives(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atlas").mkdir()
    runner_ = CliRunner()
    result = runner_.invoke(cli, ["strategy", "readiness"])
    assert result.exit_code == 0
    assert "research-only" in result.output
    assert "Promoted primitives:      0" in result.output
    assert "Live-signal generation:   blocked" in result.output


def test_cli_classification_advances_with_one_primitive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    primitives = tmp_path / ".atlas" / "primitives"
    primitives.mkdir(parents=True)
    (primitives / "p1.json").write_text(json.dumps({
        "id": "p1",
        "claim": "x",
        "hypothesis_id": "h1",
        "evidence_ids": ["e1", "e2"],
        "confidence": 0.8,
        "tags": [],
        "causal_parents": [],
    }))
    runner_ = CliRunner()
    result = runner_.invoke(cli, ["strategy", "readiness"])
    assert result.exit_code == 0
    assert "strategy-candidate" in result.output
    assert "Promoted primitives:      1" in result.output
