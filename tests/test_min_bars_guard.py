"""Regression: scan_signals must skip symbols whose dataset is shorter
than MIN_BARS_FOR_RESEARCH, emit a methodology log entry for the skip,
and exclude the symbol from cross-asset pair formation.

Motivation: SOL/USD on Bitstamp has ~3 years of 1h data vs BTC/ETH's 6+.
Before this guard, SOL/USDT entered the signal loop, produced zero signals,
and silently wasted Bonferroni budget (alpha is divided by the count of
hypotheses tested per cycle — short-history symbols that never emit
hypotheses still count against the anchor symbols if we accidentally
formulate any cross-asset signals involving them).
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from atlas.runner import MIN_BARS_FOR_RESEARCH, AutonomousRunner
from atlas.storage.event_store import EventStore
from atlas.storage.graph_store import GraphStore
from atlas.storage.state_store import StateStore


class _FakeAltData:
    def fetch_all(self) -> dict:
        return {}


class _FakeMarket:
    """Produces OHLCV frames of configurable length per symbol."""

    def __init__(self, sizes: dict[str, int]) -> None:
        self.sizes = sizes

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 0) -> pd.DataFrame:
        n = self.sizes[symbol]
        # minimal OHLCV frame — only 'close' is used downstream for signal scans
        idx = pd.date_range("2020-01-01", periods=n, freq="1h")
        return pd.DataFrame(
            {
                "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
            },
            index=idx,
        )


@pytest.fixture
def runner(tmp_path: Path, monkeypatch) -> AutonomousRunner:
    # Shrink DEFAULT_UNIVERSE to the three assets we test with.
    from atlas import runner as runner_mod

    monkeypatch.setattr(
        runner_mod, "DEFAULT_UNIVERSE",
        [("BTC/USDT", "1h"), ("ETH/USDT", "1h"), ("SOL/USDT", "1h")],
    )

    r = AutonomousRunner.__new__(AutonomousRunner)
    r.base_dir = tmp_path
    r.state = StateStore(tmp_path / ".atlas")
    r.events = EventStore(tmp_path / "sessions")
    r.graph_store = GraphStore(tmp_path / "graph")
    r.methodology_log = tmp_path / "methodology.jsonl"
    r.alt_data = _FakeAltData()
    # SOL below the floor; BTC/ETH above it.
    r.market = _FakeMarket({
        "BTC/USDT": MIN_BARS_FOR_RESEARCH + 500,
        "ETH/USDT": MIN_BARS_FOR_RESEARCH + 500,
        "SOL/USDT": MIN_BARS_FOR_RESEARCH - 1,
    })
    return r


def test_short_symbol_is_skipped_and_logged(runner: AutonomousRunner) -> None:
    runner.scan_signals()

    # Methodology log must contain a skip entry for SOL (with reason).
    entries = [
        json.loads(line) for line in runner.methodology_log.read_text().splitlines()
    ]
    sol_skips = [
        e for e in entries
        if e.get("symbol") == "SOL/USDT" and e.get("skipped") == "insufficient_history"
    ]
    assert len(sol_skips) == 1, f"expected one SOL skip entry, got {sol_skips}"
    assert sol_skips[0]["min_required"] == MIN_BARS_FOR_RESEARCH
    assert sol_skips[0]["bars"] == MIN_BARS_FOR_RESEARCH - 1


def test_long_symbols_still_scanned(runner: AutonomousRunner) -> None:
    """BTC and ETH have enough bars, so their datasets must still reach the
    in-sample frame. We can't assert on produced signals (our fake frame is
    flat), but we can assert no skip entries were written for them."""
    runner.scan_signals()

    entries = [
        json.loads(line) for line in runner.methodology_log.read_text().splitlines()
    ] if runner.methodology_log.exists() else []
    skipped_longs = [
        e for e in entries
        if e.get("skipped") == "insufficient_history"
        and e.get("symbol") in {"BTC/USDT", "ETH/USDT"}
    ]
    assert skipped_longs == []
