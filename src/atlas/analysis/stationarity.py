"""Rolling stationarity + structural-break diagnostics.

Codex review #5/#7 flagged calendar-year binning as weak for crypto regime
analysis. This module provides:

  - `rolling_correlation` — rolling Pearson r with bootstrap CI
  - `rolling_ols` — rolling OLS (alpha, beta, r2)
  - `cusum_ols` — CUSUM test on OLS recursive residuals for parameter stability
    (Brown-Durbin-Evans)
  - `chow_test` — F-test for a parameter break at a known index
  - `regime_grouped_stat` — apply a statistic within user-provided regime labels

These are diagnostic tools for research writeups, not promoted primitives.
None of the tests here should be the sole basis for a promotion decision;
they complement the walk-forward + block-bootstrap inference already used.

Design notes:
  - All functions accept aligned pandas Series (caller drops NaNs).
  - All functions return plain DataFrames / dicts so downstream code can
    serialize results into finding documents or evidence records.
  - Confidence levels are caller-supplied; default alpha=0.05.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


# -----------------------------------------------------------------------------
# Rolling statistics
# -----------------------------------------------------------------------------

def rolling_correlation(
    x: pd.Series,
    y: pd.Series,
    window: int,
    min_periods: int | None = None,
    bootstrap_ci: bool = False,
    n_boot: int = 500,
    alpha: float = 0.05,
    rng_seed: int | None = None,
) -> pd.DataFrame:
    """Rolling Pearson correlation, optional bootstrap CI per window.

    Args:
        x, y: aligned Series of equal length, no leading/trailing NaNs.
        window: number of observations per window.
        min_periods: minimum observations in a window before a value is emitted.
            Defaults to `window`.
        bootstrap_ci: if True, compute per-window percentile bootstrap CI.
        n_boot: bootstrap replications per window.
        alpha: two-sided coverage (0.05 → 95% CI).
        rng_seed: for reproducibility.

    Returns:
        DataFrame indexed like x with columns ['r'] (and ['lo', 'hi'] if
        bootstrap_ci=True). Bootstrap is percentile on (x, y) pairs within
        each window, preserving contemporaneous dependence but not serial
        dependence across windows.
    """
    min_periods = min_periods or window
    r = x.rolling(window, min_periods=min_periods).corr(y)
    if not bootstrap_ci:
        return r.to_frame("r")

    rng = np.random.default_rng(rng_seed)
    xv = x.values
    yv = y.values
    n = len(x)
    lo_arr = np.full(n, np.nan)
    hi_arr = np.full(n, np.nan)
    for i in range(min_periods - 1, n):
        start = max(0, i - window + 1)
        xi = xv[start : i + 1]
        yi = yv[start : i + 1]
        if len(xi) < min_periods:
            continue
        idx = rng.integers(0, len(xi), size=(n_boot, len(xi)))
        rs = np.empty(n_boot)
        for b in range(n_boot):
            s = idx[b]
            xb = xi[s]; yb = yi[s]
            xbm = xb - xb.mean(); ybm = yb - yb.mean()
            denom = np.sqrt((xbm**2).sum() * (ybm**2).sum())
            rs[b] = (xbm * ybm).sum() / denom if denom > 0 else np.nan
        lo_arr[i] = np.nanpercentile(rs, 100 * alpha / 2)
        hi_arr[i] = np.nanpercentile(rs, 100 * (1 - alpha / 2))
    out = pd.DataFrame({"r": r, "lo": lo_arr, "hi": hi_arr}, index=x.index)
    return out


def rolling_ols(
    x: pd.Series, y: pd.Series, window: int, min_periods: int | None = None
) -> pd.DataFrame:
    """Rolling OLS of y on x. Returns DataFrame with [alpha, beta, r2]."""
    min_periods = min_periods or window
    xm = x.rolling(window, min_periods=min_periods).mean()
    ym = y.rolling(window, min_periods=min_periods).mean()
    xv = x.rolling(window, min_periods=min_periods).var()
    cov = (x * y).rolling(window, min_periods=min_periods).mean() - xm * ym
    beta = cov / xv
    alpha = ym - beta * xm
    # r² = cov² / (var(x) * var(y))
    yv = y.rolling(window, min_periods=min_periods).var()
    r2 = (cov ** 2) / (xv * yv)
    return pd.DataFrame({"alpha": alpha, "beta": beta, "r2": r2})


# -----------------------------------------------------------------------------
# Structural-break tests
# -----------------------------------------------------------------------------

@dataclass
class CUSUMResult:
    """Brown-Durbin-Evans CUSUM test on OLS recursive residuals."""
    statistic: float          # max |W_t| where W_t is the scaled recursive residual sum
    critical_value: float     # two-sided α-level critical bound at max t
    reject_stable: bool       # True if statistic exceeds critical_value
    recursive_residuals: np.ndarray
    cusum_path: np.ndarray
    first_breach_index: int | None  # first t where |W_t| exceeds the band, or None


def cusum_ols(y: np.ndarray | pd.Series, x: np.ndarray | pd.Series,
              alpha: float = 0.05) -> CUSUMResult:
    """CUSUM test on recursive residuals of OLS y = alpha + beta * x.

    Brown-Durbin-Evans (1975) recursive residual CUSUM. Null hypothesis is
    coefficient stability across the sample.

    Critical band at significance α uses the standard approximation:
        c_α = c * sqrt(T - k) where c = 0.948 (α=0.05), 1.143 (α=0.01)
    with k = 2 parameters (alpha, beta).

    Args:
        y, x: 1D arrays/Series of aligned observations.
        alpha: significance level, 0.05 or 0.01.

    Returns:
        CUSUMResult with max absolute CUSUM, critical value, and first
        breach index (if any).
    """
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    n = len(y)
    if n < 10:
        raise ValueError(f"Need at least 10 observations, got {n}")
    k = 2  # alpha + beta

    # Recursive residuals: for each t >= k+1, fit OLS on (x[:t-1], y[:t-1])
    # and predict y[t-1], scaled by sqrt(1 + x_t' (X'X)^-1 x_t).
    recursive_resid = np.full(n, np.nan)
    sum_x = 0.0; sum_y = 0.0; sum_xx = 0.0; sum_xy = 0.0
    # Warm up with first k observations
    for i in range(k):
        sum_x += x[i]; sum_y += y[i]
        sum_xx += x[i] * x[i]; sum_xy += x[i] * y[i]
    t = k  # next index to predict
    while t < n:
        mx = sum_x / t
        my = sum_y / t
        denom = sum_xx - t * mx * mx
        if denom <= 0:
            # Degenerate: x is constant on history. Residual undefined; skip.
            sum_x += x[t]; sum_y += y[t]
            sum_xx += x[t] * x[t]; sum_xy += x[t] * y[t]
            t += 1
            continue
        beta_t = (sum_xy - t * mx * my) / denom
        alpha_t = my - beta_t * mx
        pred = alpha_t + beta_t * x[t]
        # Scale factor per B-D-E: sqrt(1 + 1/t + (x_t - mx)^2 / denom)
        scale = np.sqrt(1.0 + 1.0 / t + (x[t] - mx) ** 2 / denom)
        recursive_resid[t] = (y[t] - pred) / scale
        sum_x += x[t]; sum_y += y[t]
        sum_xx += x[t] * x[t]; sum_xy += x[t] * y[t]
        t += 1

    # Scale by estimated σ (std of valid residuals)
    r = recursive_resid[~np.isnan(recursive_resid)]
    if len(r) < 3:
        raise ValueError("Too few recursive residuals to compute CUSUM")
    # Estimate σ from full-sample OLS residuals (standard BDE choice; more
    # robust than std of recursive residuals, which inflates under a break).
    xm_full = x.mean(); ym_full = y.mean()
    denom_full = ((x - xm_full) ** 2).sum()
    if denom_full <= 0:
        raise ValueError("x has zero variance")
    b_full = ((x - xm_full) * (y - ym_full)).sum() / denom_full
    a_full = ym_full - b_full * xm_full
    resid_full = y - (a_full + b_full * x)
    sigma = float(np.sqrt((resid_full ** 2).sum() / (n - k)))
    if sigma <= 0:
        raise ValueError("Residual std is zero; cannot normalize CUSUM")
    scaled = np.where(np.isnan(recursive_resid), 0.0, recursive_resid / sigma)
    cusum = np.cumsum(scaled)

    c_val = {0.05: 0.948, 0.01: 1.143}.get(alpha)
    if c_val is None:
        raise ValueError(f"alpha must be 0.05 or 0.01, got {alpha}")
    T = n - k

    # Brown-Durbin-Evans rejects iff |W_t| crosses the widening band
    #   band(t) = c_alpha * (sqrt(T) + 2*(t-k)/sqrt(T))
    # at any t in (k, n). To give a single scalar summary that is
    # internally consistent with the rejection rule, we report the
    # argmax_t |W_t|/band(t) as the normalized statistic and compare
    # against 1.0 (reject iff > 1). The raw |W_t| at that t and the
    # band value at that t are also exposed for interpretation.
    first_breach = None
    any_breach = False
    max_norm = 0.0
    argmax_t = k + 1
    for t_idx in range(k + 1, n):
        band_t = c_val * (np.sqrt(T) + 2.0 * (t_idx - k) / np.sqrt(T))
        norm = abs(cusum[t_idx]) / band_t
        if norm > max_norm:
            max_norm = norm
            argmax_t = t_idx
        if abs(cusum[t_idx]) > band_t:
            any_breach = True
            if first_breach is None:
                first_breach = t_idx

    statistic = float(abs(cusum[argmax_t]))
    critical = float(c_val * (np.sqrt(T) + 2.0 * (argmax_t - k) / np.sqrt(T)))

    return CUSUMResult(
        statistic=statistic,
        critical_value=float(critical),
        reject_stable=bool(any_breach),
        recursive_residuals=recursive_resid,
        cusum_path=cusum,
        first_breach_index=first_breach,
    )


@dataclass
class ChowResult:
    f_statistic: float
    p_value: float
    break_index: int
    reject_stable: bool


def chow_test(y: np.ndarray | pd.Series, x: np.ndarray | pd.Series,
              break_index: int, alpha: float = 0.05) -> ChowResult:
    """Chow F-test for parameter break at `break_index` in y = a + b*x.

    H0: (a, b) is the same on [0, break_index) and [break_index, n).
    Returns F-statistic with (k, n - 2k) degrees of freedom and its p-value.
    """
    from scipy import stats

    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    n = len(y)
    k = 2
    if break_index < k + 1 or break_index > n - k - 1:
        raise ValueError(f"break_index {break_index} must leave ≥{k+1} obs on each side of n={n}")

    def rss(xi, yi):
        xm = xi.mean(); ym = yi.mean()
        xv = ((xi - xm) ** 2).sum()
        if xv <= 0:
            return float(((yi - ym) ** 2).sum()), 0.0, ym
        b = ((xi - xm) * (yi - ym)).sum() / xv
        a = ym - b * xm
        resid = yi - (a + b * xi)
        return float((resid ** 2).sum()), float(b), float(a)

    rss_full, _, _ = rss(x, y)
    rss_1, _, _ = rss(x[:break_index], y[:break_index])
    rss_2, _, _ = rss(x[break_index:], y[break_index:])
    numer = (rss_full - (rss_1 + rss_2)) / k
    denom = (rss_1 + rss_2) / (n - 2 * k)
    f = numer / denom if denom > 0 else np.inf
    p = 1 - stats.f.cdf(f, k, n - 2 * k)
    return ChowResult(
        f_statistic=float(f),
        p_value=float(p),
        break_index=int(break_index),
        reject_stable=p < alpha,
    )


# -----------------------------------------------------------------------------
# Regime-labelled grouping
# -----------------------------------------------------------------------------

def regime_grouped_stat(
    x: pd.Series,
    y: pd.Series,
    regime_labels: pd.Series,
    statfn,
    min_obs: int = 30,
) -> dict[str, dict]:
    """Apply statfn(x_sub, y_sub) within each regime label group.

    Args:
        x, y: aligned Series.
        regime_labels: Series aligned with x/y; values are regime names (strings).
        statfn: callable(x_sub, y_sub) -> dict of result fields.
        min_obs: skip regimes with fewer observations.

    Returns:
        {regime_name: {**statfn_result, 'n': count}}.
    """
    out = {}
    common = x.index.intersection(y.index).intersection(regime_labels.index)
    x_a = x.loc[common]; y_a = y.loc[common]; r_a = regime_labels.loc[common]
    for label, idx in r_a.groupby(r_a).groups.items():
        if len(idx) < min_obs:
            continue
        res = statfn(x_a.loc[idx], y_a.loc[idx])
        if not isinstance(res, dict):
            res = {"result": res}
        res["n"] = int(len(idx))
        out[str(label)] = res
    return out
