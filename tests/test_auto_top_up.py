"""Auto-top-up + INFEASIBLE feasibility check (principal decision A+C+D2,
handoff atlas-pool-rotation-decision.md, 2026-05-01).

Covers:
  - `_parse_dataset_from_hypothesis` (tag parsing for symbol/timeframe)
  - `_claim_is_permanently_infeasible` (claim-level / one-way INFEASIBLE)
  - `_data_currently_available` (reversible/environmental feasibility)
  - `_top_up_from_formulated_pool` (promote → TESTING, mark → INFEASIBLE,
    skip-but-keep-FORMULATED for environmental constraints)

Key semantic guarantee under test: a hypothesis whose data source is
temporarily unavailable (off-universe pair, insufficient bars, fetch
failure, unparseable tags) MUST stay FORMULATED so a future cycle can
re-evaluate. INFEASIBLE is reserved for permanent claim-level blocks
(geo-blocked exchanges named in the claim).
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from atlas.models.hypothesis import Hypothesis, HypothesisStatus
from atlas.runner import (
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
