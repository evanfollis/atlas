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


def _write_cycle_events(runner: AutonomousRunner, decisions_list: list[dict]):
    """Append a fake cycle.completed for each entry to the runner's
    telemetry path. Each entry: {evaluated:int, kinds:dict, ts:int}."""
    with open(runner.TELEMETRY_PATH, "a") as f:
        for entry in decisions_list:
            f.write(json.dumps({
                "project": "atlas",
                "source": "atlas.runner",
                "eventType": "cycle.completed",
                "timestamp": entry["ts"],
                "details": {
                    "hypotheses_evaluated": entry["evaluated"],
                    "decisions_by_kind": entry["kinds"],
                    "total_evidence_store_size": entry.get("evidence", 0),
                },
            }) + "\n")


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
    _write_cycle_events(r, [
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 1000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 2000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 3000},
    ])
    r._maybe_escalate_frozen_loop()
    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 1
    handoffs = list(r.HANDOFF_DIR.glob("URGENT-atlas-frozen-loop-*.md"))
    assert len(handoffs) == 1


def test_escalation_idempotent_on_same_streak(runner_with_telemetry):
    r = runner_with_telemetry
    _write_cycle_events(r, [
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 1000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 2000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 3000},
    ])
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
    same-streak cycles must NOT trigger a second cycle.escalated. The
    bug was that walk-back stopped at FROZEN_LOOP_ESCALATION_AFTER, so
    `streak_start_ts` shifted forward as cycles accumulated and
    eventually outpaced the previous escalation's timestamp, defeating
    the dedup check."""
    r = runner_with_telemetry
    _write_cycle_events(r, [
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 1000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 2000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 3000},
    ])
    r._maybe_escalate_frozen_loop()  # streak hits threshold → 1 emission

    # Now the streak grows by 3 more all-continue cycles (no break).
    _write_cycle_events(r, [
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 4000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 5000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 6000},
    ])
    r._maybe_escalate_frozen_loop()  # same streak — must NOT re-emit

    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 1, (
        "gate re-fired on a streak that never broke — dedup walks the wrong window"
    )
    handoffs = list(r.HANDOFF_DIR.glob("URGENT-atlas-frozen-loop-*.md"))
    assert len(handoffs) == 1


def test_escalation_idempotent_across_telemetry_rotation(runner_with_telemetry):
    """Regression for the 2026-04-27 02:36 false-re-emit:
    once cycle.escalated has been emitted for a streak, a midnight telemetry
    rotation that wipes the cycle.escalated event from events.jsonl must
    NOT cause the gate to re-emit. State persists in
    .atlas/escalation_state.json, not in the rotated telemetry."""
    r = runner_with_telemetry
    _write_cycle_events(r, [
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 1000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 2000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 3000},
    ])
    r._maybe_escalate_frozen_loop()  # 1st emission, state file written

    # Simulate telemetry rotation: events.jsonl is truncated. The previous
    # cycle.escalated event is gone; only the post-rotation cycle.completed
    # events remain.
    r.TELEMETRY_PATH.write_text("")
    _write_cycle_events(r, [
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 4000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 5000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 6000},
    ])
    r._maybe_escalate_frozen_loop()  # same logical streak — must NOT re-emit

    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 0, (
        "cycle.escalated event in *post-rotation* file means the gate re-fired "
        "after rotation hid the prior emission"
    )
    # The handoff was written by the FIRST call; dedup glob in
    # _write_frozen_loop_handoff prevents a second one.
    handoffs = list(r.HANDOFF_DIR.glob("URGENT-atlas-frozen-loop-*.md"))
    assert len(handoffs) == 1


def test_escalation_re_fires_after_streak_breaks_then_reforms(runner_with_telemetry):
    """Sanity check: a kill cycle resets the streak; a new 3-cycle
    all-continue run AFTER that kill (with timestamps > the prior escalation)
    must trigger a SECOND escalation. Uses wall-clock-scale timestamps so
    the dedup compares apples-to-apples with the real escalation emit time."""
    import time
    r = runner_with_telemetry
    base = int(time.time() * 1000)  # current wall clock ms
    _write_cycle_events(r, [
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": base + 1000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": base + 2000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": base + 3000},
    ])
    r._maybe_escalate_frozen_loop()  # 1st emission

    # Read back the actual escalation timestamp so the second streak's
    # cycles can be placed AFTER it (mimicking real production timing).
    first_escalated_ts = max(
        e["timestamp"] for e in _all_runner_events(r)
        if e["eventType"] == "cycle.escalated"
    )

    # Streak break: a kill cycle, then a new all-continue streak forms.
    # All these timestamps are AFTER the first escalation emit.
    _write_cycle_events(r, [
        {"evaluated": 5, "kinds": {"kill": 5}, "ts": first_escalated_ts + 1000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": first_escalated_ts + 2000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": first_escalated_ts + 3000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": first_escalated_ts + 4000},
    ])
    r._maybe_escalate_frozen_loop()  # NEW streak → SHOULD re-emit

    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 2


def test_escalation_skipped_when_kill_within_window(runner_with_telemetry):
    r = runner_with_telemetry
    _write_cycle_events(r, [
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 1000},
        {"evaluated": 5, "kinds": {"kill": 1, "continue": 4}, "ts": 2000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 3000},
    ])
    r._maybe_escalate_frozen_loop()
    types = _read_runner_event_types(r)
    assert "cycle.escalated" not in types


def test_vacuous_cycles_do_not_count(runner_with_telemetry):
    """A cycle with zero hypotheses evaluated must neither contribute to
    nor break the streak."""
    r = runner_with_telemetry
    _write_cycle_events(r, [
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 1000},
        {"evaluated": 0, "kinds": {}, "ts": 1500},  # vacuous
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 2000},
        {"evaluated": 5, "kinds": {"continue": 5}, "ts": 3000},
    ])
    r._maybe_escalate_frozen_loop()
    types = _read_runner_event_types(r)
    assert types.count("cycle.escalated") == 1


def test_escalation_threshold_constant_matches_workspace_rule():
    """Workspace CLAUDE.md S3-P2 sets the threshold to 3 consecutive
    same-reason skips. Drift here would silently weaken the gate."""
    assert FROZEN_LOOP_ESCALATION_AFTER == 3


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
