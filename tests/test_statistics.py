"""Tests for statistical tests — verify against known values."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from atlas.analysis.statistics import bootstrap_sharpe, mean_return_test, sharpe_significance


def test_mean_return_ttest_matches_scipy() -> None:
    """Our t-test should match scipy.stats.ttest_1samp."""
    np.random.seed(123)
    returns = pd.Series(np.random.normal(0.001, 0.02, 200))
    result = mean_return_test(returns, alpha=0.05)
    scipy_result = stats.ttest_1samp(returns, 0.0)
    assert abs(result.statistic - scipy_result.statistic) < 1e-10
    assert abs(result.p_value - scipy_result.pvalue) < 1e-10


def test_mean_return_significant_for_large_mean() -> None:
    """Series with a large positive mean should be significant."""
    returns = pd.Series(np.random.normal(0.05, 0.01, 500))
    result = mean_return_test(returns, alpha=0.05)
    assert result.significant
    assert result.p_value < 0.05


def test_sharpe_zero_variance() -> None:
    """Zero-variance returns → not significant, p=1."""
    returns = pd.Series([0.01] * 50)
    result = sharpe_significance(returns)
    assert result.significant is False
    assert result.p_value == 1.0


def test_sharpe_insufficient_data() -> None:
    """< 30 observations → not significant."""
    returns = pd.Series(np.random.normal(0.01, 0.02, 20))
    result = sharpe_significance(returns)
    assert result.significant is False


def test_bootstrap_ci_contains_point_estimate() -> None:
    """Bootstrap CI should contain the point Sharpe estimate (most of the time)."""
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.001, 0.02, 300))
    result = bootstrap_sharpe(returns, alpha=0.05)
    # Point estimate should be within the 95% CI
    assert result.ci_lower <= result.statistic <= result.ci_upper


def test_bootstrap_zero_mean_not_significant() -> None:
    """Zero-mean returns → bootstrap should not be significant."""
    np.random.seed(7)
    returns = pd.Series(np.random.normal(0.0, 0.02, 500))
    result = bootstrap_sharpe(returns, alpha=0.05)
    # CI should cross zero (not significant)
    assert result.ci_lower < 0


def test_bootstrap_negative_sharpe_significant() -> None:
    """Strongly negative Sharpe should be significant (two-sided test)."""
    np.random.seed(42)
    returns = pd.Series(np.random.normal(-0.005, 0.01, 500))
    result = bootstrap_sharpe(returns, periods_per_year=252, alpha=0.05)
    assert result.significant
    assert result.ci_upper < 0


def test_sharpe_significance_positive_sharpe() -> None:
    """A strongly positive Sharpe should be significant."""
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.005, 0.01, 1000))
    result = sharpe_significance(returns, periods_per_year=252, alpha=0.05)
    assert result.significant
    assert result.details["sharpe"] > 0
