"""Tests for the forward-prediction ledger.

Phase 2a locks the schema (bucketed ids, forward-only windows, dedup-on-read).
Phase 2b locks the scorer: replay the frozen spec on the forward window only,
write conservative (never-STRONG) live_observation evidence, resolve append-only.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from atlas.generation.signals import Signal
from atlas.models.evidence import EvidenceClass, EvidenceQuality
from atlas.models.prediction import Prediction, prediction_id
from atlas.runner import AutonomousRunner, PREDICTION_HORIZON_DAYS
from atlas.storage.prediction_store import PredictionStore
from atlas.storage.state_store import StateStore


def _autocorr_signal(symbol: str = "BTC/USDT", tf: str = "1h", lag: int = 1) -> Signal:
    return Signal(
        description="lag autocorrelation",
        method="autocorrelation_scan",
        strength=0.5,
        symbol=symbol,
        timeframe=tf,
        metadata={"lag": lag, "autocorr": 0.12},
    )


def test_prediction_id_buckets_are_stable_and_distinct() -> None:
    a = prediction_id("hyp-1", 7.0, 100)
    a_again = prediction_id("hyp-1", 7.0, 100)
    next_bucket = prediction_id("hyp-1", 7.0, 101)
    other_claim = prediction_id("hyp-2", 7.0, 100)

    assert a == a_again            # same (claim, horizon, bucket) -> idempotent
    assert a != next_bucket        # different window -> distinct prediction
    assert a != other_claim        # different claim -> distinct prediction


def test_prediction_id_is_stable_across_int_float_horizon() -> None:
    # 7 and 7.0 are the same logical horizon and must not fork the id.
    assert prediction_id("hyp-1", 7, 100) == prediction_id("hyp-1", 7.0, 100)


def test_invalid_horizon_is_rejected() -> None:
    import pytest

    for bad in (0, -1, float("nan")):
        with pytest.raises(ValueError):
            prediction_id("hyp-1", bad, 100)
        with pytest.raises(ValueError):
            Prediction.forward_bucket(datetime(2026, 6, 28, tzinfo=timezone.utc), bad)


def test_forward_bucket_window_is_entirely_in_the_future() -> None:
    now = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    bucket, window_start, resolve = Prediction.forward_bucket(now, 7.0)

    assert window_start > now       # the scored window has not started yet
    assert resolve > window_start
    # the window is exactly one horizon long
    assert (resolve - window_start).total_seconds() == 7.0 * 86400

    # every cycle within the same horizon window yields the same bucket
    later_same_window = now.replace(hour=23)
    assert Prediction.forward_bucket(later_same_window, 7.0)[0] == bucket


def test_store_dedups_on_read_and_filters(tmp_path: Path) -> None:
    store = PredictionStore(tmp_path / "predictions.jsonl")
    now = datetime(2026, 6, 28, tzinfo=timezone.utc)
    bucket, ws, rs = Prediction.forward_bucket(now, 7.0)
    p = Prediction(
        id="p1", hypothesis_id="h1", claim="c", symbol="BTC/USDT", timeframe="1h",
        strategy_tags=["btc_usdt", "1h", "autocorrelation"], horizon_days=7.0,
        bucket=bucket, window_start_ts=ws, resolve_ts=rs, asof_ts=now, statement="s",
    )
    store.append(p)
    assert store.exists("p1")
    assert store.count_open() == 1

    # resolution appends an updated record; last-write-wins on read
    p.status = "resolved"
    store.update(p)
    assert len(store.all()) == 1
    assert store.count_open() == 0
    assert store.list_due(rs) == []  # resolved no longer due


def test_register_predictions_is_idempotent_across_cycles(tmp_path: Path) -> None:
    r = AutonomousRunner.__new__(AutonomousRunner)
    r.predictions = PredictionStore(tmp_path / "predictions.jsonl")
    r.methodology_log = tmp_path / "methodology.jsonl"
    # _emit_telemetry writes to a class-level path; stub it out for the unit test.
    r._emit_telemetry = lambda *a, **k: None

    now = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    signal_results = [("BTC/USDT", "1h", [_autocorr_signal()], None)]

    first = r.register_predictions(signal_results, now=now)
    # Re-run within the same horizon window (a later hour) — must not duplicate.
    second = r.register_predictions(signal_results, now=now.replace(hour=20))

    assert first["registered"] == 1
    assert second["registered"] == 0
    assert r.predictions.count_open() == 1

    # A frozen spec was captured so the 2b scorer can replay without re-fitting.
    pred = r.predictions.all()[0]
    assert pred.symbol == "BTC/USDT" and pred.timeframe == "1h"
    assert "autocorrelation" in pred.strategy_tags
    assert pred.status == "open"
    assert pred.window_start_ts > now


def test_register_skips_unreplayable_methods(tmp_path: Path) -> None:
    """Cross-asset/lead-lag/calendar/composite reconstruct as proxy or fallback,
    not the actual claim — they must not be forward-scored until the spec
    captures what they need."""
    r = AutonomousRunner.__new__(AutonomousRunner)
    r.predictions = PredictionStore(tmp_path / "predictions.jsonl")
    r.methodology_log = tmp_path / "methodology.jsonl"
    r._emit_telemetry = lambda *a, **k: None

    now = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    cross_asset = Signal(
        description="spread reverts", method="cross_asset_spread", strength=0.5,
        symbol="BTC/USDT", timeframe="1h", metadata={"partner": "ETH/USDT"},
    )
    signal_results = [("BTC/USDT", "1h", [_autocorr_signal(), cross_asset], None)]

    result = r.register_predictions(signal_results, now=now)

    assert result["registered"] == 1            # only the single-source signal
    assert result["skipped_unreplayable"] == 1  # cross-asset deferred
    assert all("pairs_trading" not in p.strategy_tags for p in r.predictions.all())


def test_register_logs_which_signal_was_skipped_as_unreplayable(tmp_path: Path) -> None:
    """A bare `skipped_unreplayable: N` count cannot tell the by-design
    deferral of cross_asset_spread/lead_lag apart from a regression that
    silently drops a genuinely-replayable method. The skip must be
    attributable: method + symbol + timeframe of every dropped signal."""
    r = AutonomousRunner.__new__(AutonomousRunner)
    r.predictions = PredictionStore(tmp_path / "predictions.jsonl")
    r.methodology_log = tmp_path / "methodology.jsonl"
    r._emit_telemetry = lambda *a, **k: None

    now = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    cross_asset = Signal(
        description="spread reverts", method="cross_asset_spread", strength=0.5,
        symbol="BTC/USDT", timeframe="1h", metadata={"partner": "ETH/USDT"},
    )
    lead_lag = Signal(
        description="eth leads btc", method="lead_lag", strength=0.5,
        symbol="ETH/USDT", timeframe="1h", metadata={},
    )
    signal_results = [("BTC/USDT", "1h", [_autocorr_signal(), cross_asset, lead_lag], None)]

    result = r.register_predictions(signal_results, now=now)

    assert result["skipped_unreplayable"] == 2
    detail = result["skipped_unreplayable_detail"]
    methods = {d["method"] for d in detail}
    assert methods == {"cross_asset_spread", "lead_lag"}
    # Every dropped signal is fully identified, not just counted.
    assert all({"method", "symbol", "timeframe"} <= set(d) for d in detail)
    assert {d["symbol"] for d in detail} == {"BTC/USDT", "ETH/USDT"}


# --- Phase 2b: scorer ---

class _StubMarket:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def fetch_ohlcv(self, symbol=None, timeframe=None, since=None, limit=100000):
        return self._df


def _ohlcv(start: datetime, periods: int) -> pd.DataFrame:
    """Deterministic 1h OHLCV with non-degenerate return variance."""
    idx = pd.date_range(start=start, periods=periods, freq="1h", tz="UTC")
    x = 100.0
    closes = []
    for i in range(periods):
        x *= 1 + 0.002 * ((i * 13 % 7) - 3)  # oscillating ~[-0.6%, +0.8%]
        closes.append(x)
    close = pd.Series(closes, index=idx)
    df = pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999,
         "close": close, "volume": 1000.0},
        index=idx,
    )
    df.index.name = "timestamp"
    return df


def _due_prediction(now: datetime, horizon: float = 7.0):
    past = now - timedelta(days=30)  # a window that resolved well before `now`
    bucket, ws, rs = Prediction.forward_bucket(past, horizon)
    pid = prediction_id("h-x", horizon, bucket)
    p = Prediction(
        id=pid, hypothesis_id="h-x",
        claim="BTC/USDT 1h returns show negative autocorrelation at lag 1, enabling a mean-reversion strategy",
        symbol="BTC/USDT", timeframe="1h",
        strategy_tags=["btc_usdt", "1h", "autocorrelation", "mean_reversion"],
        horizon_days=horizon, bucket=bucket, window_start_ts=ws, resolve_ts=rs,
        asof_ts=past, statement="s",
    )
    return p, ws, rs


def _scorer_runner(tmp_path: Path, df: pd.DataFrame) -> AutonomousRunner:
    r = AutonomousRunner.__new__(AutonomousRunner)
    r.predictions = PredictionStore(tmp_path / "predictions.jsonl")
    r.state = StateStore(tmp_path / ".atlas")
    r.market = _StubMarket(df)
    r.methodology_log = tmp_path / "methodology.jsonl"
    r._emit_telemetry = lambda *a, **k: None
    return r


def test_scorer_resolves_and_writes_live_observation(tmp_path: Path) -> None:
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    pred, ws, _ = _due_prediction(now)
    df = _ohlcv(ws - timedelta(days=8), 24 * 22)  # covers warm-up + window
    r = _scorer_runner(tmp_path, df)
    r.predictions.append(pred)

    result = r.score_due_predictions(now=now)

    assert result["scored"] == 1
    resolved = r.predictions.all()[0]
    assert resolved.status == "resolved"
    assert resolved.realized_sharpe is not None and resolved.realized_return is not None
    assert resolved.outcome in ("confirmed_null", "edge_appeared", "inconclusive")
    # append-only: the forecast fields must be untouched by resolution
    assert resolved.claim == pred.claim
    assert resolved.window_start_ts == pred.window_start_ts
    assert resolved.predicted_prob_up == 0.5
    # one live_observation evidence, linked to the prediction, and NEVER strong
    evs = r.state.list_all("evidence")
    assert len(evs) == 1
    assert evs[0]["evidence_class"] == EvidenceClass.LIVE_OBSERVATION.value
    assert evs[0]["quality"] in (EvidenceQuality.WEAK.value, EvidenceQuality.MODERATE.value)
    assert evs[0]["experiment_id"] == pred.id
    assert r.predictions.count_open() == 0


def test_scorer_marks_insufficient_data_unresolvable(tmp_path: Path) -> None:
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    pred, ws, _ = _due_prediction(now)
    df = _ohlcv(ws, 20)  # far fewer than SCORE_MIN_BARS in the window
    r = _scorer_runner(tmp_path, df)
    r.predictions.append(pred)

    result = r.score_due_predictions(now=now)

    assert result["unresolvable"] == 1 and result["scored"] == 0
    assert r.predictions.all()[0].status == "unresolvable"
    assert r.state.list_all("evidence") == []


def test_scorer_leaves_future_predictions_open(tmp_path: Path) -> None:
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    bucket, ws, rs = Prediction.forward_bucket(now, 7.0)  # window is in the future
    fut = Prediction(
        id="p-future", hypothesis_id="h", claim="c", symbol="BTC/USDT", timeframe="1h",
        strategy_tags=["btc_usdt", "1h", "autocorrelation"], horizon_days=7.0,
        bucket=bucket, window_start_ts=ws, resolve_ts=rs, asof_ts=now, statement="s",
    )
    r = _scorer_runner(tmp_path, _ohlcv(now - timedelta(days=8), 24 * 22))
    r.predictions.append(fut)

    result = r.score_due_predictions(now=now)

    assert result["scored"] == 0 and result["unresolvable"] == 0
    assert r.predictions.all()[0].status == "open"
