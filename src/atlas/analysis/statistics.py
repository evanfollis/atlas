"""Statistical tests for research evidence quality."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class SignificanceResult:
    test_name: str
    statistic: float
    p_value: float
    significant: bool  # At the pre-registered threshold
    ci_lower: float
    ci_upper: float
    details: dict


def sharpe_significance(
    returns: pd.Series,
    benchmark_sharpe: float = 0.0,
    periods_per_year: float = 365 * 6,
    alpha: float = 0.05,
) -> SignificanceResult:
    """Test whether Sharpe ratio is significantly different from benchmark.

    Uses simplified iid/normal SE approximation. Does NOT adjust for
    autocorrelation (Lo 2002) — p-values may be optimistic for serially
    correlated returns. Treat as a lower bound on uncertainty.
    """
    n = len(returns)
    mean_r = returns.mean()
    std_r = returns.std()

    if std_r == 0 or n < 30:
        return SignificanceResult(
            test_name="sharpe_significance",
            statistic=0.0,
            p_value=1.0,
            significant=False,
            ci_lower=0.0,
            ci_upper=0.0,
            details={"error": "insufficient data or zero variance"},
        )

    sharpe = mean_r / std_r * np.sqrt(periods_per_year)

    # Standard error of Sharpe (simplified — assumes normal returns)
    se_sharpe = np.sqrt((1 + 0.5 * sharpe**2) / n) * np.sqrt(periods_per_year)

    t_stat = (sharpe - benchmark_sharpe) / se_sharpe
    p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df=n - 1))

    ci_lower = sharpe - stats.t.ppf(1 - alpha / 2, df=n - 1) * se_sharpe
    ci_upper = sharpe + stats.t.ppf(1 - alpha / 2, df=n - 1) * se_sharpe

    return SignificanceResult(
        test_name="sharpe_significance",
        statistic=t_stat,
        p_value=p_value,
        significant=p_value < alpha,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        details={"sharpe": sharpe, "se": se_sharpe, "n": n},
    )


def mean_return_test(
    returns: pd.Series,
    benchmark_mean: float = 0.0,
    alpha: float = 0.05,
) -> SignificanceResult:
    """One-sample t-test on mean returns vs benchmark."""
    result = stats.ttest_1samp(returns.dropna(), benchmark_mean)
    n = len(returns.dropna())
    mean_r = returns.mean()
    se = returns.std() / np.sqrt(n)
    t_crit = stats.t.ppf(1 - alpha / 2, df=n - 1)

    return SignificanceResult(
        test_name="mean_return_ttest",
        statistic=float(result.statistic),
        p_value=float(result.pvalue),
        significant=result.pvalue < alpha,
        ci_lower=float(mean_r - t_crit * se),
        ci_upper=float(mean_r + t_crit * se),
        details={"mean": float(mean_r), "se": float(se), "n": n},
    )


def bootstrap_sharpe(
    returns: pd.Series,
    periods_per_year: float = 365 * 6,
    n_bootstrap: int = 10000,
    alpha: float = 0.05,
    block_size: int | None = None,
) -> SignificanceResult:
    """Stationary block bootstrap confidence interval for Sharpe ratio.

    Uses random-length contiguous blocks (geometric distribution) to preserve
    serial dependence in returns. This is more honest than iid resampling for
    financial time series, where returns exhibit autocorrelation and volatility
    clustering.

    Args:
        block_size: Expected block length. Defaults to int(sqrt(n)), a common
            choice for stationary block bootstrap. Larger values preserve more
            serial structure but reduce resampling variation.
    """
    rng = np.random.default_rng(42)
    n = len(returns)
    values = returns.values

    if block_size is None:
        block_size = max(1, int(np.sqrt(n)))

    # Probability of ending a block at each step (geometric distribution)
    p_end = 1.0 / block_size

    sharpes = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        # Build sample by concatenating random-length contiguous blocks
        sample = np.empty(n)
        pos = 0
        while pos < n:
            # Random start position (wrap-around for stationarity)
            start = rng.integers(0, n)
            # Geometric block length
            length = rng.geometric(p_end)
            length = min(length, n - pos)
            # Extract block with wrap-around
            for j in range(length):
                sample[pos] = values[(start + j) % n]
                pos += 1

        mean_s = sample.mean()
        std_s = sample.std()
        sharpes[i] = mean_s / std_s * np.sqrt(periods_per_year) if std_s > 0 else 0.0

    point_sharpe = returns.mean() / returns.std() * np.sqrt(periods_per_year) if returns.std() > 0 else 0.0
    ci_lower = float(np.percentile(sharpes, 100 * alpha / 2))
    ci_upper = float(np.percentile(sharpes, 100 * (1 - alpha / 2)))

    # Two-sided p-value: test whether Sharpe is significantly different from zero
    # This allows the bootstrap to flag both positive AND negative strategies
    p_positive = float(np.mean(sharpes <= 0))  # P(Sharpe <= 0)
    p_negative = float(np.mean(sharpes >= 0))  # P(Sharpe >= 0)
    p_value = 2.0 * min(p_positive, p_negative)  # two-sided
    p_value = min(p_value, 1.0)

    # Significant if CI excludes zero in either direction
    ci_excludes_zero = ci_lower > 0 or ci_upper < 0

    return SignificanceResult(
        test_name="block_bootstrap_sharpe",
        statistic=float(point_sharpe),
        p_value=p_value,
        significant=ci_excludes_zero,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        details={
            "point_sharpe": float(point_sharpe),
            "n_bootstrap": n_bootstrap,
            "n": n,
            "block_size": block_size,
        },
    )
