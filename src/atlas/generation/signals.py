"""Signal intake — scan market data for testable patterns.

Signals are raw observations that might lead to hypotheses.
Each signal records the detection method and its provenance.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd


@dataclass
class Signal:
    description: str
    method: str  # How it was detected
    strength: float  # 0-1
    symbol: str
    timeframe: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)


def detect_regime_change(prices: pd.Series, window: int = 50) -> list[Signal]:
    """Detect volatility regime changes using rolling std ratio.

    Scans the entire series for regime transitions, not just the latest bar.
    Reports the most extreme regime change observed as a structural pattern.
    """
    signals = []
    if len(prices) < window * 2:
        return signals

    vol_short = prices.pct_change().rolling(window // 2).std()
    vol_long = prices.pct_change().rolling(window).std()
    ratio = (vol_short / vol_long).dropna()

    if len(ratio) == 0:
        return signals

    # Count how often regime changes occur across the series
    n_expansions = int((ratio > 1.5).sum())
    n_compressions = int((ratio < 0.5).sum())
    n_total = len(ratio)

    if n_expansions > n_total * 0.05:  # >5% of bars show expansion
        peak = float(ratio.max())
        signals.append(Signal(
            description=f"Recurrent volatility expansion: {n_expansions}/{n_total} bars above 1.5x ratio (peak {peak:.2f})",
            method="rolling_vol_ratio",
            strength=min(1.0, n_expansions / n_total),
            symbol="",
            timeframe="",
            metadata={"vol_ratio_peak": peak, "n_expansions": n_expansions, "window": window},
        ))
    if n_compressions > n_total * 0.05:
        trough = float(ratio.min())
        signals.append(Signal(
            description=f"Recurrent volatility compression: {n_compressions}/{n_total} bars below 0.5x ratio (trough {trough:.2f})",
            method="rolling_vol_ratio",
            strength=min(1.0, n_compressions / n_total),
            symbol="",
            timeframe="",
            metadata={"vol_ratio_trough": trough, "n_compressions": n_compressions, "window": window},
        ))

    return signals


def detect_autocorrelation(returns: pd.Series, max_lag: int = 10) -> list[Signal]:
    """Detect significant autocorrelation in returns (potential predictability)."""
    signals = []
    if len(returns) < max_lag + 30:
        return signals

    clean = returns.dropna()
    n = len(clean)
    threshold = 2.0 / np.sqrt(n)  # Approximate 95% CI for white noise

    for lag in range(1, max_lag + 1):
        ac = clean.autocorr(lag=lag)
        if abs(ac) > threshold:
            signals.append(Signal(
                description=f"Significant autocorrelation at lag {lag}: r={ac:.3f} (threshold ±{threshold:.3f})",
                method="autocorrelation_scan",
                strength=min(1.0, abs(ac) / threshold - 1.0),
                symbol="",
                timeframe="",
                metadata={"lag": lag, "autocorr": float(ac), "threshold": float(threshold)},
            ))

    return signals


def detect_mean_reversion(prices: pd.Series, windows: list[int] | None = None) -> list[Signal]:
    """Detect mean-reversion tendency: do extreme z-scores tend to revert?

    Instead of checking the latest bar's z-score, this tests whether prices
    historically revert after hitting extreme z-scores — a structural pattern
    that can be tested out of sample.
    """
    signals = []
    if windows is None:
        windows = [50, 100]

    for w in windows:
        if len(prices) < w * 2:
            continue
        ma = prices.rolling(w).mean()
        std = prices.rolling(w).std()
        z = ((prices - ma) / std).dropna()
        if len(z) < w:
            continue

        # Check: after |z| > 2, does z move back toward 0 within w//2 bars?
        extreme_mask = z.abs() > 2.0
        n_extremes = int(extreme_mask.sum())
        if n_extremes < 5:
            continue  # not enough events to judge

        # For each extreme, check if z-score magnitude decreased within lookforward
        lookforward = w // 2
        reversions = 0
        for idx in z.index[extreme_mask]:
            pos = z.index.get_loc(idx)
            if pos + lookforward >= len(z):
                continue
            future_z = z.iloc[pos + 1: pos + lookforward + 1]
            if future_z.abs().min() < abs(z.iloc[pos]) * 0.5:
                reversions += 1

        reversion_rate = reversions / n_extremes if n_extremes > 0 else 0
        if reversion_rate > 0.5:
            signals.append(Signal(
                description=f"Mean reversion after extreme deviations: {reversion_rate:.0%} revert within {lookforward} bars ({w}-period MA, {n_extremes} events)",
                method="zscore_mean_reversion",
                strength=min(1.0, (reversion_rate - 0.4) / 0.4),
                symbol="",
                timeframe="",
                metadata={"window": w, "reversion_rate": float(reversion_rate), "n_extremes": n_extremes, "lookforward": lookforward},
            ))

    return signals


def detect_volume_anomaly(df: pd.DataFrame, window: int = 20) -> list[Signal]:
    """Detect volume-return relationship: do volume spikes predict directional moves?"""
    signals = []
    if len(df) < window * 3 or "volume" not in df.columns:
        return signals

    vol_ma = df["volume"].rolling(window).mean()
    vol_std = df["volume"].rolling(window).std()
    vol_z = ((df["volume"] - vol_ma) / vol_std).dropna()
    returns = df["close"].pct_change()

    if len(vol_z) < window:
        return signals

    # Check: do high-volume bars (z > 2) predict above-average next-bar returns?
    spike_mask = vol_z > 2.0
    n_spikes = int(spike_mask.sum())
    if n_spikes < 5:
        return signals

    # Next-bar returns after volume spikes (align indices)
    next_returns = returns.shift(-1).dropna()
    common = spike_mask.index.intersection(next_returns.index)
    spike_next_returns = next_returns.loc[common[spike_mask.loc[common]]]
    normal_returns = returns.dropna()

    if len(spike_next_returns) < 3:
        return signals

    spike_mean = float(spike_next_returns.mean())
    normal_mean = float(normal_returns.mean())
    spike_abs_mean = float(spike_next_returns.abs().mean())
    normal_abs_mean = float(normal_returns.abs().mean())

    # Volume spikes predict larger absolute moves (regardless of direction)
    if spike_abs_mean > normal_abs_mean * 1.5 and n_spikes >= 5:
        signals.append(Signal(
            description=f"Volume spikes predict {spike_abs_mean/normal_abs_mean:.1f}x larger moves ({n_spikes} events)",
            method="volume_return_relationship",
            strength=min(1.0, (spike_abs_mean / normal_abs_mean - 1.0) / 2.0),
            symbol="",
            timeframe="",
            metadata={"n_spikes": n_spikes, "spike_abs_return": spike_abs_mean, "normal_abs_return": normal_abs_mean},
        ))

    return signals


def detect_momentum_persistence(returns: pd.Series, lookbacks: list[int] | None = None) -> list[Signal]:
    """Detect whether multi-bar returns predict next-bar direction.

    Tests: does sign(return over last K bars) predict sign(next bar return)?
    This captures momentum/mean-reversion at multiple horizons without
    relying on single-lag autocorrelation thresholds.
    """
    signals = []
    if lookbacks is None:
        lookbacks = [5, 10, 20]

    clean = returns.dropna()
    n = len(clean)
    if n < 100:
        return signals

    for k in lookbacks:
        if n < k + 50:
            continue
        rolling_ret = clean.rolling(k).sum().dropna()
        # Align: rolling_ret[t] predicts clean[t+1]
        aligned = pd.DataFrame({
            "signal": rolling_ret.iloc[:-1].values,
            "next_ret": clean.iloc[k:k + len(rolling_ret) - 1].values,
        })
        if len(aligned) < 50:
            continue

        # Hit rate: does sign(signal) == sign(next_ret)?
        same_sign = ((aligned["signal"] > 0) & (aligned["next_ret"] > 0)) | \
                    ((aligned["signal"] < 0) & (aligned["next_ret"] < 0))
        hit_rate = float(same_sign.mean())

        # Test against 50% baseline (binomial)
        from scipy import stats as sp_stats
        n_obs = len(aligned)
        n_hits = int(same_sign.sum())
        p_value = sp_stats.binomtest(n_hits, n_obs, 0.5).pvalue

        if p_value < 0.10:  # lenient threshold — the hypothesis will be properly tested OOS
            direction = "momentum" if hit_rate > 0.5 else "reversal"
            signals.append(Signal(
                description=f"{k}-bar {direction}: {hit_rate:.1%} directional hit rate (p={p_value:.3f}, n={n_obs})",
                method="momentum_persistence",
                strength=min(1.0, abs(hit_rate - 0.5) / 0.1),
                symbol="",
                timeframe="",
                metadata={"lookback": k, "hit_rate": hit_rate, "p_value": p_value, "direction": direction, "n_obs": n_obs},
            ))

    return signals


def detect_return_skew(returns: pd.Series) -> list[Signal]:
    """Detect significant skew in return distribution.

    Positive skew suggests asymmetric upside; negative skew suggests crash risk.
    Either can be exploited with options-like strategies or tail-hedging.
    """
    signals = []
    clean = returns.dropna()
    n = len(clean)
    if n < 100:
        return signals

    from scipy.stats import skewtest
    stat, p_value = skewtest(clean)
    skew = float(clean.skew())

    if p_value < 0.05:
        direction = "positive" if skew > 0 else "negative"
        signals.append(Signal(
            description=f"Significant {direction} skew: {skew:.3f} (p={p_value:.4f}, n={n})",
            method="return_skew",
            strength=min(1.0, abs(skew) / 1.0),
            symbol="",
            timeframe="",
            metadata={"skew": skew, "p_value": p_value, "direction": direction},
        ))

    return signals


def detect_volatility_clustering(returns: pd.Series) -> list[Signal]:
    """Detect GARCH-like volatility clustering: high vol predicts high vol.

    Tests autocorrelation of absolute returns. Strong clustering means
    volatility is predictable, enabling position-sizing strategies.
    """
    signals = []
    clean = returns.dropna()
    n = len(clean)
    if n < 100:
        return signals

    abs_r = clean.abs()
    threshold = 2.0 / np.sqrt(n)

    ac1 = abs_r.autocorr(1)
    ac5 = abs_r.autocorr(5)

    if abs(ac1) > threshold * 2:  # require 2x threshold for robustness
        signals.append(Signal(
            description=f"Volatility clustering: |returns| autocorr lag1={ac1:.3f}, lag5={ac5:.3f} (n={n})",
            method="volatility_clustering",
            strength=min(1.0, abs(ac1) / 0.3),
            symbol="",
            timeframe="",
            metadata={"ac_lag1": float(ac1), "ac_lag5": float(ac5), "n": n},
        ))

    return signals


def detect_cross_asset_spread(
    prices_a: pd.Series, prices_b: pd.Series,
    symbol_a: str, symbol_b: str,
    window: int = 50,
) -> list[Signal]:
    """Detect mean reversion in cross-asset price ratio.

    The ratio of two correlated assets often mean-reverts even when
    individual assets don't, because market-wide factors cancel out.
    """
    signals = []
    common = prices_a.index.intersection(prices_b.index)
    if len(common) < window * 2:
        return signals

    ratio = prices_a.loc[common] / prices_b.loc[common]
    ratio_z = (ratio - ratio.rolling(window).mean()) / ratio.rolling(window).std()
    rz = ratio_z.dropna()

    if len(rz) < window:
        return signals

    # Test: do extreme ratios revert?
    extreme_mask = rz.abs() > 1.5
    n_extremes = int(extreme_mask.sum())
    if n_extremes < 10:
        return signals

    lookforward = window // 2
    reversions = 0
    for idx in rz.index[extreme_mask]:
        pos = rz.index.get_loc(idx)
        if pos + lookforward >= len(rz):
            continue
        future = rz.iloc[pos + 1: pos + lookforward + 1]
        if future.abs().min() < abs(rz.iloc[pos]) * 0.5:
            reversions += 1

    reversion_rate = reversions / n_extremes
    if reversion_rate > 0.5:
        signals.append(Signal(
            description=f"{symbol_a}/{symbol_b} spread reverts: {reversion_rate:.0%} of {n_extremes} extreme events revert within {lookforward} bars",
            method="cross_asset_spread",
            strength=min(1.0, (reversion_rate - 0.4) / 0.4),
            symbol="",
            timeframe="",
            metadata={
                "symbol_a": symbol_a, "symbol_b": symbol_b,
                "reversion_rate": float(reversion_rate),
                "n_extremes": n_extremes, "window": window,
            },
        ))

    return signals


def detect_lead_lag(
    returns_a: pd.Series, returns_b: pd.Series,
    symbol_a: str, symbol_b: str,
) -> list[Signal]:
    """Detect lead-lag relationship: does asset A predict asset B's next return?"""
    signals = []
    common = returns_a.index.intersection(returns_b.index)
    if len(common) < 100:
        return signals

    a = returns_a.loc[common]
    b = returns_b.loc[common]

    # A[t] predicts B[t+1]
    x = a.iloc[:-1].values
    y = b.iloc[1:].values

    from scipy.stats import pearsonr
    corr, pval = pearsonr(x, y)

    if pval < 0.05 and abs(corr) > 0.05:
        leader, follower = symbol_a, symbol_b
        signals.append(Signal(
            description=f"{leader} leads {follower}: corr={corr:.4f} (p={pval:.4f}, n={len(x)})",
            method="lead_lag",
            strength=min(1.0, abs(corr) / 0.15),
            symbol="",
            timeframe="",
            metadata={
                "leader": leader, "follower": follower,
                "correlation": float(corr), "p_value": float(pval),
                "n": len(x),
            },
        ))

    return signals


def scan_all(df: pd.DataFrame, universe_data: dict | None = None) -> list[Signal]:
    """Run all signal detectors on a price DataFrame.

    Args:
        df: Primary OHLCV DataFrame.
        universe_data: Optional dict of {(symbol, timeframe): DataFrame} for
            cross-asset detectors. If None, only single-asset detectors run.
    """
    signals = []
    prices = df["close"]
    returns = prices.pct_change().dropna()

    signals.extend(detect_regime_change(prices))
    signals.extend(detect_autocorrelation(returns))
    signals.extend(detect_mean_reversion(prices))
    signals.extend(detect_volume_anomaly(df))
    signals.extend(detect_momentum_persistence(returns))
    signals.extend(detect_return_skew(returns))
    signals.extend(detect_volatility_clustering(returns))

    return signals
