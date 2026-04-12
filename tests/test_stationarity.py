"""Tests for stationarity / structural-break diagnostics."""

import numpy as np
import pandas as pd
import pytest

from atlas.analysis.stationarity import (
    rolling_correlation,
    rolling_ols,
    cusum_ols,
    chow_test,
    regime_grouped_stat,
)


def test_rolling_correlation_basic() -> None:
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(0, 1, 200))
    y = 0.5 * x + pd.Series(rng.normal(0, 1, 200))
    out = rolling_correlation(x, y, window=50)
    valid = out["r"].dropna()
    assert len(valid) == 151  # 200 - 50 + 1
    # Should be positive on balance because true correlation > 0
    assert valid.mean() > 0.2


def test_rolling_correlation_bootstrap_ci_contains_point() -> None:
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(0, 1, 150))
    y = 0.3 * x + pd.Series(rng.normal(0, 1, 150))
    out = rolling_correlation(x, y, window=80, bootstrap_ci=True,
                              n_boot=100, rng_seed=1)
    valid = out.dropna()
    assert len(valid) > 0
    # Each window's point estimate should lie inside its own CI most of the time.
    inside = ((valid["r"] >= valid["lo"]) & (valid["r"] <= valid["hi"])).mean()
    assert inside > 0.85


def test_rolling_ols_beta_recovers_truth() -> None:
    rng = np.random.default_rng(2)
    x = pd.Series(rng.normal(0, 1, 300))
    y = 0.7 * x + pd.Series(rng.normal(0, 0.1, 300))
    out = rolling_ols(x, y, window=100)
    assert abs(out["beta"].dropna().mean() - 0.7) < 0.05


def test_cusum_rejects_on_known_break() -> None:
    rng = np.random.default_rng(3)
    n = 500
    x = rng.normal(0, 1, n)
    y = np.empty(n)
    # Regime 1: beta = +2.0; Regime 2: beta = -2.0
    y[:250] = 2.0 * x[:250] + rng.normal(0, 0.2, 250)
    y[250:] = -2.0 * x[250:] + rng.normal(0, 0.2, 250)
    result = cusum_ols(y, x, alpha=0.05)
    assert result.reject_stable, (
        f"CUSUM should reject stability on planted break; "
        f"stat={result.statistic:.2f}, crit={result.critical_value:.2f}"
    )


def test_cusum_accepts_stable_series() -> None:
    rng = np.random.default_rng(4)
    n = 300
    x = rng.normal(0, 1, n)
    y = 0.4 * x + rng.normal(0, 0.3, n)
    result = cusum_ols(y, x, alpha=0.05)
    # Under a truly stable DGP the max CUSUM is usually well inside the band.
    assert result.statistic < result.critical_value * 1.1


def test_chow_test_rejects_on_break() -> None:
    rng = np.random.default_rng(5)
    x = rng.normal(0, 1, 200)
    y = np.concatenate([
        0.5 * x[:100] + rng.normal(0, 0.2, 100),
        -0.5 * x[100:] + rng.normal(0, 0.2, 100),
    ])
    res = chow_test(y, x, break_index=100)
    assert res.reject_stable
    assert res.p_value < 0.01


def test_chow_test_accepts_no_break() -> None:
    rng = np.random.default_rng(6)
    x = rng.normal(0, 1, 200)
    y = 0.4 * x + rng.normal(0, 0.3, 200)
    res = chow_test(y, x, break_index=100)
    assert not res.reject_stable


def test_regime_grouped_stat_dispatches() -> None:
    rng = np.random.default_rng(7)
    x = pd.Series(rng.normal(0, 1, 150))
    y = pd.Series(rng.normal(0, 1, 150))
    labels = pd.Series(["bull"] * 50 + ["bear"] * 50 + ["range"] * 50)

    def stat(xs, ys):
        return {"mean_y": float(ys.mean()), "mean_x": float(xs.mean())}

    out = regime_grouped_stat(x, y, labels, stat, min_obs=30)
    assert set(out.keys()) == {"bull", "bear", "range"}
    assert all(out[r]["n"] == 50 for r in out)


def test_regime_grouped_stat_skips_small_groups() -> None:
    x = pd.Series(np.zeros(100))
    y = pd.Series(np.zeros(100))
    labels = pd.Series(["a"] * 10 + ["b"] * 90)
    out = regime_grouped_stat(x, y, labels, lambda a, b: {"k": 1}, min_obs=30)
    assert "a" not in out
    assert "b" in out


def test_chow_test_rejects_invalid_break_index() -> None:
    x = np.arange(100, dtype=float)
    y = x * 0.5
    with pytest.raises(ValueError):
        chow_test(y, x, break_index=1)
