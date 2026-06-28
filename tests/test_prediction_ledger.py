"""Tests for the forward-prediction ledger (Phase 2a: registration + storage).

Locks the three load-bearing schema decisions: bucketed (non-overlapping,
idempotent) ids, forward-only windows, and dedup-on-read storage. Scoring (2b)
and the calibration CLI (2c) are separate.
"""

from datetime import datetime, timezone
from pathlib import Path

from atlas.generation.signals import Signal
from atlas.models.prediction import Prediction, prediction_id
from atlas.runner import AutonomousRunner, PREDICTION_HORIZON_DAYS
from atlas.storage.prediction_store import PredictionStore


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
