"""Tests for signal detectors — synthetic data that triggers each detector."""

import numpy as np
import pandas as pd

from atlas.generation.signals import (
    detect_autocorrelation,
    detect_mean_reversion,
    detect_regime_change,
    detect_volume_anomaly,
    scan_all,
)


def test_autocorrelation_detects_ar1() -> None:
    """AR(1) process with high coefficient should trigger autocorrelation signal."""
    np.random.seed(42)
    n = 500
    returns = np.zeros(n)
    for i in range(1, n):
        returns[i] = 0.5 * returns[i - 1] + np.random.normal(0, 0.01)
    signals = detect_autocorrelation(pd.Series(returns))
    assert len(signals) > 0
    assert any(s.method == "autocorrelation_scan" for s in signals)


def test_autocorrelation_white_noise() -> None:
    """White noise should not trigger autocorrelation (usually)."""
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0, 0.01, 500))
    signals = detect_autocorrelation(returns)
    # Might get one spurious detection but shouldn't get many
    assert len(signals) <= 2


def test_mean_reversion_structural() -> None:
    """Prices that revert after extreme z-scores should trigger."""
    np.random.seed(42)
    # Long stable period then sharp spikes that revert — creates extreme z-scores
    stable = np.full(200, 100.0) + np.random.normal(0, 0.5, 200)
    # Add sharp spikes that revert: 10 events
    for i in range(50, 200, 15):
        stable[i] = 100 + 10  # spike up to ~3+ sigma
        stable[i + 1] = 100    # immediate reversion
    prices = pd.Series(stable)
    signals = detect_mean_reversion(prices, windows=[50])
    assert len(signals) > 0
    assert any("revert" in s.description.lower() for s in signals)


def test_mean_reversion_no_signal_in_normal_range() -> None:
    """Price near MA should not trigger."""
    prices = pd.Series(np.linspace(100, 102, 100))
    signals = detect_mean_reversion(prices, windows=[20])
    assert len(signals) == 0


def test_regime_change_volatility_compression() -> None:
    """Volatility compression (high → calm) should trigger regime change.

    The detector fires when rolling(W//2)/rolling(W) < 0.5. This happens
    when the recent half-window is much calmer than the full window.
    """
    np.random.seed(42)
    # 100 bars volatile, then exactly 25 calm bars — window=50
    # At the last bar: short(25) is all calm, long(50) is half volatile + half calm
    # So ratio = tiny_std / mixed_std < 0.5
    volatile_returns = np.random.normal(0, 0.10, 100)
    calm_returns = np.random.normal(0, 0.0001, 25)
    all_returns = np.concatenate([volatile_returns, calm_returns])
    prices = pd.Series(100 * np.exp(np.cumsum(all_returns)))
    signals = detect_regime_change(prices, window=50)
    assert len(signals) > 0
    assert "compression" in signals[0].description.lower()


def test_volume_spike_predicts_moves() -> None:
    """Volume spikes followed by large moves should trigger."""
    np.random.seed(42)
    n = 200
    volume = np.random.uniform(1000, 2000, n)
    close = np.cumsum(np.random.normal(0, 0.5, n)) + 100
    # Insert volume spikes followed by big moves at regular intervals
    for i in range(20, n - 1, 20):
        volume[i] = 20000  # spike
        close[i + 1] = close[i] + np.random.choice([-3, 3])  # big move after
    df = pd.DataFrame({"close": close, "volume": volume})
    signals = detect_volume_anomaly(df, window=20)
    assert len(signals) > 0
    assert signals[0].method == "volume_return_relationship"


def test_volume_anomaly_no_column() -> None:
    """Missing volume column should return empty."""
    df = pd.DataFrame({"close": np.linspace(100, 110, 50)})
    signals = detect_volume_anomaly(df)
    assert signals == []


def test_scan_all_returns_list() -> None:
    """scan_all should return a list (possibly empty) for any valid dataframe."""
    np.random.seed(42)
    df = pd.DataFrame({
        "close": np.random.normal(100, 1, 200),
        "volume": np.random.uniform(1000, 2000, 200),
    })
    signals = scan_all(df)
    assert isinstance(signals, list)
