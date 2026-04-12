"""Tests for curated events + event-study framework."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from atlas.data.events import EVENTS, events_in_scope
from atlas.analysis.event_study import event_study


def test_events_have_required_fields() -> None:
    for e in EVENTS:
        assert e.date.tzinfo is timezone.utc
        assert e.category
        assert e.scope
        assert e.label
        assert e.source


def test_events_in_scope_filter() -> None:
    btc_hv = events_in_scope("BTC", category="halving")
    assert len(btc_hv) >= 3
    assert all(e.category == "halving" and "BTC" in e.scope for e in btc_hv)
    # Sorted ascending
    dates = [e.date for e in btc_hv]
    assert dates == sorted(dates)


def test_event_study_detects_planted_shock() -> None:
    rng = np.random.default_rng(0)
    n = 2000
    base = pd.Series(
        rng.normal(0, 0.01, n),
        index=pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC"),
    )
    # Inject a +3% return at 5 specific bars
    event_idxs = [300, 600, 900, 1200, 1500]
    for i in event_idxs:
        base.iloc[i] = 0.03
    events = [base.index[i].to_pydatetime() for i in event_idxs]

    res = event_study(base, events, pre=5, post=20, car_window=(0, 0),
                      n_controls=500, buffer=30, rng_seed=0)
    # CAR at k=0 should be ~+3%
    assert res.mean_event_car > 0.02
    assert res.p_two_sided < 0.05


def test_event_study_null_dgp_fails_to_reject() -> None:
    rng = np.random.default_rng(1)
    n = 2000
    base = pd.Series(
        rng.normal(0, 0.01, n),
        index=pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC"),
    )
    events = [base.index[i].to_pydatetime() for i in [300, 600, 900, 1200, 1500]]
    res = event_study(base, events, pre=5, post=20, n_controls=500, rng_seed=1)
    # Under the null, observed CAR should not sit deep in the control tails
    assert res.p_two_sided > 0.05


def test_event_study_rejects_bad_window() -> None:
    base = pd.Series(
        np.zeros(200),
        index=pd.date_range("2020-01-01", periods=200, freq="h", tz="UTC"),
    )
    with pytest.raises(ValueError):
        event_study(base, [base.index[50].to_pydatetime()],
                    pre=5, post=10, car_window=(-20, 5))


def test_event_study_drops_edge_events() -> None:
    base = pd.Series(
        np.zeros(100),
        index=pd.date_range("2020-01-01", periods=100, freq="h", tz="UTC"),
    )
    # All events too close to edges → should raise
    edge_events = [base.index[2].to_pydatetime(), base.index[97].to_pydatetime()]
    with pytest.raises(ValueError, match="No events fit"):
        event_study(base, edge_events, pre=10, post=10)
