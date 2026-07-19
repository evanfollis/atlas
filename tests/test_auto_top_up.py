"""Auto-top-up + INFEASIBLE feasibility check (principal decision A+C+D2,
handoff atlas-pool-rotation-decision.md, 2026-05-01) plus P1 orphaned-
TESTING re-evaluation (supervisor dispatch atlas-testing-reeval-p1-
2026-05-02T16-48Z.md).

Covers:
  - `_parse_dataset_from_hypothesis` (tag parsing for symbol/timeframe)
  - `_claim_is_permanently_infeasible` (claim-level / one-way INFEASIBLE)
  - `_data_currently_available` (reversible/environmental feasibility)
  - `_top_up_from_formulated_pool` (promote → TESTING, mark → INFEASIBLE,
    skip-but-keep-FORMULATED for environmental constraints)
  - `_include_orphaned_testing` (re-include TESTING with unfresh dataset;
    cap and ordering interactions with top-up)

Key semantic guarantee under test: a hypothesis whose data source is
temporarily unavailable (off-universe pair, insufficient bars, fetch
failure, unparseable tags) MUST stay FORMULATED so a future cycle can
re-evaluate. INFEASIBLE is reserved for permanent claim-level blocks
(geo-blocked exchanges named in the claim).

P1 invariant under test: `_include_orphaned_testing` MUST run before
`_top_up_from_formulated_pool`. Reversed, the top-up fills slots first
and TESTING starves forever (the failure mode observed 2026-05-02).
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from atlas.models.evidence import (
    Evidence,
    EvidenceClass,
    EvidenceDirection,
    EvidenceQuality,
)
from atlas.models.experiment import Experiment
from atlas.models.hypothesis import Hypothesis, HypothesisStatus
from atlas.runner import (
    DATASET_RETEST_AFTER,
    MIN_BARS_FOR_RESEARCH,
    TOP_UP_TARGET,
    AutonomousRunner,
)
from atlas.storage.event_store import EventStore
from atlas.storage.graph_store import GraphStore
from atlas.storage.state_store import StateStore


class _FakeMarket:
    def __init__(self, sizes: dict[tuple[str, str], int]) -> None:
        self.sizes = sizes
        self.calls: list[tuple[str, str]] = []

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 0) -> pd.DataFrame:
        self.calls.append((symbol, timeframe))
        n = self.sizes.get((symbol, timeframe), 0)
        if n == 0:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        idx = pd.date_range("2020-01-01", periods=n, freq="1h")
        return pd.DataFrame(
            {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
            index=idx,
        )


@pytest.fixture
def runner(tmp_path: Path) -> AutonomousRunner:
    r = AutonomousRunner.__new__(AutonomousRunner)
    r.base_dir = tmp_path
    r.state = StateStore(tmp_path / ".atlas")
    r.events = EventStore(tmp_path / "sessions")
    r.graph_store = GraphStore(tmp_path / "graph")
    r.methodology_log = tmp_path / "methodology.jsonl"
    r.market = _FakeMarket({
        ("BTC/USDT", "1h"): MIN_BARS_FOR_RESEARCH + 500,
        ("ETH/USDT", "1h"): MIN_BARS_FOR_RESEARCH + 500,
        ("SOL/USDT", "1h"): MIN_BARS_FOR_RESEARCH - 1,  # below floor
    })
    # Route telemetry into the tmp dir so the test never writes into
    # /opt/workspace/runtime.
    r.TELEMETRY_PATH = tmp_path / ".telemetry" / "events.jsonl"
    r.HANDOFF_DIR = tmp_path / ".handoff"
    return r


# --- _parse_dataset_from_hypothesis -----------------------------------------


def test_parse_dataset_from_tags_returns_symbol_timeframe() -> None:
    h = Hypothesis(
        claim="weekend volatility lower",
        rationale="r",
        falsification_criteria="f",
        tags=["btc_usdt", "1h", "calendar"],
    )
    assert AutonomousRunner._parse_dataset_from_hypothesis(h) == ("BTC/USDT", "1h")


def test_parse_dataset_returns_none_when_timeframe_missing() -> None:
    h = Hypothesis(
        claim="x", rationale="r", falsification_criteria="f",
        tags=["btc_usdt", "calendar"],
    )
    assert AutonomousRunner._parse_dataset_from_hypothesis(h) is None


def test_parse_dataset_returns_none_when_symbol_missing() -> None:
    h = Hypothesis(
        claim="x", rationale="r", falsification_criteria="f",
        tags=["1h", "calendar"],
    )
    assert AutonomousRunner._parse_dataset_from_hypothesis(h) is None


# --- _claim_is_permanently_infeasible (one-way door) ------------------------


def test_claim_infeasible_for_bitmex_in_claim() -> None:
    h = Hypothesis(
        claim="BitMEX funding z-score predicts BTC return",
        rationale="r", falsification_criteria="f", tags=["btc_usdt", "1h"],
    )
    assert AutonomousRunner._claim_is_permanently_infeasible(h) is True


def test_claim_infeasible_for_kraken_futures() -> None:
    h = Hypothesis(
        claim="Kraken Futures perp basis predicts spot return",
        rationale="r", falsification_criteria="f", tags=["btc_usdt", "1h"],
    )
    assert AutonomousRunner._claim_is_permanently_infeasible(h) is True


def test_claim_infeasible_for_binance_in_tag() -> None:
    h = Hypothesis(
        claim="generic spot signal", rationale="r", falsification_criteria="f",
        tags=["btc_usdt", "1h", "binance"],
    )
    assert AutonomousRunner._claim_is_permanently_infeasible(h) is True


def test_claim_not_infeasible_when_no_blocked_exchange() -> None:
    h = Hypothesis(
        claim="BTC weekend volatility lower", rationale="r",
        falsification_criteria="f", tags=["btc_usdt", "1h"],
    )
    assert AutonomousRunner._claim_is_permanently_infeasible(h) is False


# --- _data_currently_available (reversible / environmental) -----------------


def test_data_available_for_btc_1h(runner: AutonomousRunner) -> None:
    h = Hypothesis(
        claim="BTC weekend volatility lower", rationale="r",
        falsification_criteria="f", tags=["btc_usdt", "1h"],
    )
    assert runner._data_currently_available(h) is True


def test_data_unavailable_for_offuniverse_timeframe(runner: AutonomousRunner) -> None:
    h = Hypothesis(
        claim="ETH 4h end-of-month drift", rationale="r",
        falsification_criteria="f", tags=["eth_usdt", "4h"],
    )
    assert runner._data_currently_available(h) is False


def test_data_unavailable_for_insufficient_bars(runner: AutonomousRunner) -> None:
    h = Hypothesis(
        claim="SOL weekend volatility", rationale="r",
        falsification_criteria="f", tags=["sol_usdt", "1h"],
    )
    assert runner._data_currently_available(h) is False


def test_data_unavailable_for_unparseable_tags(runner: AutonomousRunner) -> None:
    h = Hypothesis(
        claim="Pure cross-asset signal — no symbol", rationale="r",
        falsification_criteria="f", tags=[],
    )
    assert runner._data_currently_available(h) is False


# --- _top_up_from_formulated_pool -------------------------------------------


def _save_h(r: AutonomousRunner, claim: str, tags: list[str], status: HypothesisStatus) -> Hypothesis:
    h = Hypothesis(
        claim=claim, rationale="r", falsification_criteria="f", tags=tags,
        status=status,
    )
    r._save_obj("hypotheses", h.id, h.model_dump())
    return h


def test_top_up_promotes_feasible_to_testing(runner: AutonomousRunner) -> None:
    feasible = _save_h(runner, "BTC weekend skip", ["btc_usdt", "1h"],
                       HypothesisStatus.FORMULATED)

    out = runner._top_up_from_formulated_pool([])

    assert len(out) == 1
    assert out[0].id == feasible.id
    assert out[0].status == HypothesisStatus.TESTING
    persisted = runner._load_obj("hypotheses", feasible.id)
    assert persisted["status"] == HypothesisStatus.TESTING.value


def test_top_up_marks_claim_infeasible_in_storage(runner: AutonomousRunner) -> None:
    """Claim-level infeasibility (geo-blocked exchange) is a one-way door."""
    bad = _save_h(runner, "BitMEX funding signal", ["btc_usdt", "1h"],
                  HypothesisStatus.FORMULATED)

    out = runner._top_up_from_formulated_pool([])

    assert out == []  # nothing promoted
    persisted = runner._load_obj("hypotheses", bad.id)
    assert persisted["status"] == HypothesisStatus.INFEASIBLE.value


def test_top_up_keeps_environmentally_blocked_as_formulated(runner: AutonomousRunner) -> None:
    """SOL/USDT 1h has only MIN_BARS-1 bars in the fake market today, but
    that's environmental, not claim-level. The hypothesis must stay
    FORMULATED so a future cycle can re-evaluate when the bar count
    catches up."""
    sol = _save_h(runner, "SOL weekend skip", ["sol_usdt", "1h"],
                  HypothesisStatus.FORMULATED)
    eth_4h = _save_h(runner, "ETH end-of-month 4h drift", ["eth_usdt", "4h"],
                     HypothesisStatus.FORMULATED)
    no_tags = _save_h(runner, "graph-gap with no tags", [],
                      HypothesisStatus.FORMULATED)

    out = runner._top_up_from_formulated_pool([])

    assert out == []  # none promoted
    for h in (sol, eth_4h, no_tags):
        persisted = runner._load_obj("hypotheses", h.id)
        assert persisted["status"] == HypothesisStatus.FORMULATED.value, \
            f"{h.id} should remain FORMULATED, not INFEASIBLE"


def test_pool_skip_reason_classifies_each_block_type() -> None:
    """Parse-only classifier that makes `skipped_not_promotable` attributable.
    Must distinguish a structural block (off-universe timeframe like an
    orphaned 4h claim) from a transient one (in-universe pair still filling
    its bar history) — the two demand different operator responses."""
    def h(tags: list[str]) -> Hypothesis:
        return Hypothesis(claim="c", rationale="r", falsification_criteria="f", tags=tags)

    assert AutonomousRunner._pool_skip_reason(h([])) == "unparseable_tags"
    assert AutonomousRunner._pool_skip_reason(h(["eth_usdt", "4h"])) == "off_universe_timeframe"
    assert AutonomousRunner._pool_skip_reason(h(["sol_usdt", "1h"])) == "insufficient_bars_or_fetch"


def test_top_up_logs_per_hypothesis_skip_reason(runner: AutonomousRunner) -> None:
    """The methodology log must record *which* hypotheses were skipped and
    *why*, so a permanently-stuck pool (all off_universe_timeframe) is
    diagnosable rather than an opaque `skipped_not_promotable: N`."""
    import json

    sol = _save_h(runner, "SOL weekend skip", ["sol_usdt", "1h"], HypothesisStatus.FORMULATED)
    eth_4h = _save_h(runner, "ETH 4h drift", ["eth_usdt", "4h"], HypothesisStatus.FORMULATED)

    runner._top_up_from_formulated_pool([])

    entries = [json.loads(line) for line in runner.methodology_log.read_text().splitlines()]
    top_up = next(e for e in entries if e.get("phase") == "auto_top_up")
    detail = {d["id"]: d["reason"] for d in top_up["skipped_not_promotable_detail"]}
    assert detail[sol.id] == "insufficient_bars_or_fetch"
    assert detail[eth_4h.id] == "off_universe_timeframe"


def test_top_up_cleans_infeasible_even_when_target_filled(runner: AutonomousRunner) -> None:
    """Even when `current` is already at TOP_UP_TARGET, claim-level
    infeasible entries in the pool MUST be marked — otherwise the pool
    accumulates dead weight that never gets cleaned up."""
    bad = _save_h(runner, "BitMEX funding signal", ["btc_usdt", "1h"],
                  HypothesisStatus.FORMULATED)

    current = [
        Hypothesis(claim=f"existing-{i}", rationale="r", falsification_criteria="f")
        for i in range(TOP_UP_TARGET)
    ]
    runner._top_up_from_formulated_pool(current)

    persisted = runner._load_obj("hypotheses", bad.id)
    assert persisted["status"] == HypothesisStatus.INFEASIBLE.value


def test_top_up_skips_already_resolved_statuses(runner: AutonomousRunner) -> None:
    """Only FORMULATED hypotheses are eligible for top-up — TESTING,
    PROMOTED, FALSIFIED, INFEASIBLE must be left alone."""
    _save_h(runner, "already-testing", ["btc_usdt", "1h"], HypothesisStatus.TESTING)
    _save_h(runner, "already-promoted", ["btc_usdt", "1h"], HypothesisStatus.PROMOTED)
    _save_h(runner, "already-falsified", ["btc_usdt", "1h"], HypothesisStatus.FALSIFIED)
    _save_h(runner, "already-infeasible", ["btc_usdt", "1h"], HypothesisStatus.INFEASIBLE)

    out = runner._top_up_from_formulated_pool([])

    assert out == []


def test_top_up_caps_at_target(runner: AutonomousRunner) -> None:
    # Save TOP_UP_TARGET + 2 feasible hypotheses
    for i in range(TOP_UP_TARGET + 2):
        _save_h(runner, f"BTC strategy {i}", ["btc_usdt", "1h"],
                HypothesisStatus.FORMULATED)

    out = runner._top_up_from_formulated_pool([])
    assert len(out) == TOP_UP_TARGET


def test_top_up_no_promote_when_current_already_full(runner: AutonomousRunner) -> None:
    feasible = _save_h(runner, "BTC weekend skip", ["btc_usdt", "1h"],
                       HypothesisStatus.FORMULATED)

    # Current cycle already at TOP_UP_TARGET — top-up must not promote.
    current = [
        Hypothesis(claim=f"existing-{i}", rationale="r", falsification_criteria="f")
        for i in range(TOP_UP_TARGET)
    ]
    out = runner._top_up_from_formulated_pool(current)
    assert len(out) == TOP_UP_TARGET

    persisted = runner._load_obj("hypotheses", feasible.id)
    assert persisted["status"] == HypothesisStatus.FORMULATED.value


def test_top_up_logs_methodology_entry(runner: AutonomousRunner) -> None:
    _save_h(runner, "BTC weekend skip", ["btc_usdt", "1h"], HypothesisStatus.FORMULATED)
    _save_h(runner, "BitMEX signal", ["btc_usdt", "1h"], HypothesisStatus.FORMULATED)
    _save_h(runner, "ETH 4h drift", ["eth_usdt", "4h"], HypothesisStatus.FORMULATED)

    runner._top_up_from_formulated_pool([])

    entries = [
        json.loads(line) for line in runner.methodology_log.read_text().splitlines()
    ]
    top_ups = [e for e in entries if e.get("phase") == "auto_top_up"]
    assert len(top_ups) == 1
    assert len(top_ups[0]["promoted_from_formulated"]) == 1
    assert len(top_ups[0]["marked_infeasible"]) == 1
    assert len(top_ups[0]["skipped_not_promotable"]) == 1
    assert top_ups[0]["pool_size"] == 3


def test_top_up_emits_telemetry_for_any_pool_activity(runner: AutonomousRunner) -> None:
    """Telemetry must fire whenever the pool was non-empty — including when
    every candidate is environmentally blocked. Otherwise frozen-loop
    monitor goes blind to the 'pool full of stuck-but-not-INFEASIBLE'
    failure mode the reviewer flagged."""
    _save_h(runner, "ETH 4h drift", ["eth_usdt", "4h"], HypothesisStatus.FORMULATED)

    runner._top_up_from_formulated_pool([])

    events = [
        json.loads(line) for line in runner.TELEMETRY_PATH.read_text().splitlines()
    ]
    top_up_events = [e for e in events if e.get("eventType") == "cycle.top_up"]
    assert len(top_up_events) == 1
    assert top_up_events[0]["details"]["promoted"] == 0
    assert top_up_events[0]["details"]["skipped_not_promotable"] == 1
    assert top_up_events[0]["details"]["pool_size"] == 1


def test_top_up_no_telemetry_when_pool_empty(runner: AutonomousRunner) -> None:
    """When the FORMULATED pool itself is empty, top-up must stay silent —
    nothing happened, no event needed."""
    runner._top_up_from_formulated_pool([])
    assert not runner.TELEMETRY_PATH.exists()


# --- _include_orphaned_testing (P1) -----------------------------------------


def _save_evidence_for(
    r: AutonomousRunner,
    h: Hypothesis,
    symbol: str,
    timeframe: str,
    age: timedelta,
) -> None:
    """Persist an experiment + evidence record marking (symbol, timeframe)
    as fresh-tested for `h` at `now - age`."""
    exp = Experiment(
        hypothesis_id=h.id,
        description="x",
        method="backtest",
        parameters={"symbol": symbol, "timeframe": timeframe},
        success_criteria="s",
        failure_criteria="f",
    )
    r._save_obj("experiments", exp.id, exp.model_dump())

    ev = Evidence(
        experiment_id=exp.id,
        hypothesis_id=h.id,
        evidence_class=EvidenceClass.OUT_OF_SAMPLE_TEST,
        quality=EvidenceQuality.WEAK,
        direction=EvidenceDirection.INCONCLUSIVE,
        summary="x",
        created_at=datetime.now(timezone.utc) - age,
    )
    r._save_obj("evidence", ev.id, ev.model_dump())


def test_include_orphaned_testing_includes_when_unfresh_universe_has_data(
    runner: AutonomousRunner,
) -> None:
    """TESTING hypothesis tested only on BTC/USDT 1h within the freshness
    window — ETH/USDT 1h is unfresh AND has ≥ MIN_BARS_FOR_RESEARCH
    bars in the fake market, so re-include."""
    h = _save_h(runner, "weekend skip", ["btc_usdt", "1h"], HypothesisStatus.TESTING)
    _save_evidence_for(runner, h, "BTC/USDT", "1h", age=timedelta(hours=1))

    out = runner._include_orphaned_testing([])

    assert len(out) == 1
    assert out[0].id == h.id


def test_include_orphaned_testing_skips_when_only_unfresh_dataset_has_no_data(
    runner: AutonomousRunner,
) -> None:
    """Productivity gate: only SOL is unfresh, but SOL has < MIN_BARS in
    the fake market. Re-eval must skip — not burn a slot for a
    hypothesis that will produce zero experiments. This is the
    2026-05-02 production state of the 7 orphaned TESTING hypotheses."""
    h = _save_h(runner, "weekend skip", ["btc_usdt", "1h"], HypothesisStatus.TESTING)
    for sym, tf in [("BTC/USDT", "1h"), ("ETH/USDT", "1h")]:
        _save_evidence_for(runner, h, sym, tf, age=timedelta(hours=1))
    # SOL is unfresh but the fake market gives it MIN_BARS - 1.

    out = runner._include_orphaned_testing([])

    assert out == []


def test_include_orphaned_testing_skips_when_all_universe_fresh(
    runner: AutonomousRunner,
) -> None:
    """If every DEFAULT_UNIVERSE dataset has fresh evidence for this
    hypothesis, there is nothing new to learn this cycle — skip."""
    h = _save_h(runner, "weekend skip", ["btc_usdt", "1h"], HypothesisStatus.TESTING)
    for sym, tf in [("BTC/USDT", "1h"), ("ETH/USDT", "1h"), ("SOL/USDT", "1h")]:
        _save_evidence_for(runner, h, sym, tf, age=timedelta(hours=1))

    out = runner._include_orphaned_testing([])

    assert out == []


def test_include_orphaned_testing_includes_when_evidence_is_stale(
    runner: AutonomousRunner,
) -> None:
    """Evidence older than DATASET_RETEST_AFTER does NOT count as fresh.
    The hypothesis must be re-included even when every universe dataset
    has prior evidence, as long as that evidence has aged out — provided
    at least one universe dataset has sufficient bars."""
    h = _save_h(runner, "weekend skip", ["btc_usdt", "1h"], HypothesisStatus.TESTING)
    stale = DATASET_RETEST_AFTER + timedelta(hours=1)
    for sym, tf in [("BTC/USDT", "1h"), ("ETH/USDT", "1h"), ("SOL/USDT", "1h")]:
        _save_evidence_for(runner, h, sym, tf, age=stale)

    out = runner._include_orphaned_testing([])

    assert len(out) == 1


def test_include_orphaned_testing_skips_claim_infeasible(
    runner: AutonomousRunner,
) -> None:
    """A TESTING hypothesis whose claim names a geo-blocked exchange (e.g.
    ingested via research/ingest with BitMEX in the claim, never
    migrated) must be skipped — re-eval doesn't auto-migrate to
    INFEASIBLE (that's an ingest-contract decision), but it must not
    burn a slot every cycle either."""
    h = _save_h(runner, "BitMEX funding signal", ["btc_usdt", "1h"],
                HypothesisStatus.TESTING)

    out = runner._include_orphaned_testing([])

    assert out == []
    persisted = runner._load_obj("hypotheses", h.id)
    assert persisted["status"] == HypothesisStatus.TESTING.value, \
        "re-eval must NOT auto-migrate ingested TESTING to INFEASIBLE"


def test_include_orphaned_testing_skips_non_testing_statuses(
    runner: AutonomousRunner,
) -> None:
    """Only TESTING-status hypotheses are eligible. FORMULATED, PROMOTED,
    FALSIFIED, INFEASIBLE must be left out."""
    _save_h(runner, "f", ["btc_usdt", "1h"], HypothesisStatus.FORMULATED)
    _save_h(runner, "p", ["btc_usdt", "1h"], HypothesisStatus.PROMOTED)
    _save_h(runner, "x", ["btc_usdt", "1h"], HypothesisStatus.FALSIFIED)
    _save_h(runner, "i", ["btc_usdt", "1h"], HypothesisStatus.INFEASIBLE)

    out = runner._include_orphaned_testing([])

    assert out == []


def test_include_orphaned_testing_does_not_double_add(
    runner: AutonomousRunner,
) -> None:
    """If a TESTING hypothesis is already in `current` (e.g. picked up by
    generate_hypotheses because its signal happened to re-fire), it
    must not be added a second time."""
    h = _save_h(runner, "weekend skip", ["btc_usdt", "1h"], HypothesisStatus.TESTING)

    out = runner._include_orphaned_testing([h])

    assert len(out) == 1
    assert out[0].id == h.id


def test_include_orphaned_testing_caps_at_target(runner: AutonomousRunner) -> None:
    """Slot budget shared with top-up via TOP_UP_TARGET — if there are
    more orphaned TESTING than slots remain, only fill what fits."""
    for i in range(TOP_UP_TARGET + 3):
        _save_h(runner, f"strategy {i}", ["btc_usdt", "1h"], HypothesisStatus.TESTING)

    out = runner._include_orphaned_testing([])

    assert len(out) == TOP_UP_TARGET


def test_include_orphaned_testing_no_op_when_current_full(
    runner: AutonomousRunner,
) -> None:
    """If `current` is already at TOP_UP_TARGET, no TESTING re-eval
    happens this cycle — the budget is exhausted by signal-driven work."""
    h = _save_h(runner, "weekend skip", ["btc_usdt", "1h"], HypothesisStatus.TESTING)

    current = [
        Hypothesis(claim=f"existing-{i}", rationale="r", falsification_criteria="f")
        for i in range(TOP_UP_TARGET)
    ]
    out = runner._include_orphaned_testing(current)
    assert len(out) == TOP_UP_TARGET
    assert h.id not in [c.id for c in out]


def test_include_orphaned_testing_emits_telemetry(runner: AutonomousRunner) -> None:
    h_productive = _save_h(runner, "productive", ["btc_usdt", "1h"],
                           HypothesisStatus.TESTING)
    h_all_fresh = _save_h(runner, "all-fresh", ["eth_usdt", "1h"],
                          HypothesisStatus.TESTING)
    h_infeasible = _save_h(runner, "BitMEX claim", ["btc_usdt", "1h"],
                           HypothesisStatus.TESTING)
    for sym, tf in [("BTC/USDT", "1h"), ("ETH/USDT", "1h"), ("SOL/USDT", "1h")]:
        _save_evidence_for(runner, h_all_fresh, sym, tf, age=timedelta(hours=1))

    runner._include_orphaned_testing([])

    events = [
        json.loads(line) for line in runner.TELEMETRY_PATH.read_text().splitlines()
    ]
    reeval_events = [e for e in events if e.get("eventType") == "cycle.testing_reeval"]
    assert len(reeval_events) == 1
    details = reeval_events[0]["details"]
    assert details["re_included_productive"] == 1
    assert details["skipped_no_productive_dataset"] == 1
    assert details["skipped_claim_infeasible"] == 1
    assert details["pool_size"] == 3
    _ = h_productive
    _ = h_infeasible


def test_include_orphaned_testing_no_telemetry_when_pool_empty(
    runner: AutonomousRunner,
) -> None:
    """No TESTING hypotheses in storage → no event emitted."""
    runner._include_orphaned_testing([])
    assert not runner.TELEMETRY_PATH.exists()


def test_include_orphaned_testing_runs_before_top_up_in_run_cycle() -> None:
    """The ordering invariant is enforced by code structure, not by a
    runtime guard. This test asserts the source has the methods called
    in the correct order — if a future refactor swaps them, the loop
    will starve as observed 2026-05-02. Catching that in CI is cheaper
    than catching it in production."""
    import inspect

    from atlas import runner as runner_mod

    source = inspect.getsource(runner_mod.AutonomousRunner.run_cycle)
    pos_reeval = source.find("_include_orphaned_testing")
    pos_topup = source.find("_top_up_from_formulated_pool")
    assert 0 < pos_reeval < pos_topup, (
        f"_include_orphaned_testing must be called before "
        f"_top_up_from_formulated_pool in run_cycle "
        f"(reeval@{pos_reeval}, topup@{pos_topup})"
    )
