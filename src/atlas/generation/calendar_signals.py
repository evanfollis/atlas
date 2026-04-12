"""Calendar effect detectors — temporal patterns from institutional flows.

Causal mechanism: traditional finance markets close on weekends/holidays,
crypto markets do not. Institutional rebalancing flows cluster around
month-end and US business hours. These produce systematic effects
that are causally grounded in market microstructure, not statistical accident.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from atlas.generation.signals import Signal


def detect_end_of_month(prices: pd.Series, eom_window: int = 3) -> list[Signal]:
    """Detect end-of-month return drift.

    Mechanism: institutional rebalancing at month-end forces selling of
    outperforming assets to maintain allocation targets. Crypto being a
    high-vol asset means it's often the one being trimmed.
    """
    signals = []
    if len(prices) < 200:
        return signals

    returns = prices.pct_change().dropna()
    dom = returns.index.day
    eom_mask = dom >= (31 - eom_window + 1)  # last N days

    eom_returns = returns[eom_mask]
    other_returns = returns[~eom_mask]

    if len(eom_returns) < 30 or len(other_returns) < 100:
        return signals

    # Welch's t-test for difference in means
    t_stat, p_value = sp_stats.ttest_ind(eom_returns, other_returns, equal_var=False)

    if p_value < 0.10:
        diff = float(eom_returns.mean() - other_returns.mean())
        direction = "negative" if diff < 0 else "positive"
        signals.append(Signal(
            description=f"End-of-month {direction} drift: EOM mean={eom_returns.mean()*100:.3f}%/bar "
                        f"vs other={other_returns.mean()*100:.3f}%/bar (p={p_value:.3f}, n_eom={len(eom_returns)})",
            method="end_of_month_effect",
            strength=min(1.0, abs(t_stat) / 3.0),
            symbol="", timeframe="",
            metadata={
                "eom_mean": float(eom_returns.mean()),
                "other_mean": float(other_returns.mean()),
                "diff": diff,
                "direction": direction,
                "p_value": float(p_value),
                "n_eom": len(eom_returns),
                "eom_window_days": eom_window,
            },
        ))

    return signals


def detect_weekend_effect(prices: pd.Series) -> list[Signal]:
    """Detect weekend return/volatility effects.

    Mechanism: traditional markets closed → reduced institutional flow,
    thinner liquidity, retail-dominated trading. Volatility typically
    lower but tail risk can be higher (no institutional support during shocks).
    """
    signals = []
    if len(prices) < 200:
        return signals

    returns = prices.pct_change().dropna()
    dow = returns.index.dayofweek
    weekend_mask = dow.isin([5, 6])

    weekend_returns = returns[weekend_mask]
    weekday_returns = returns[~weekend_mask]

    if len(weekend_returns) < 50 or len(weekday_returns) < 100:
        return signals

    # Test mean return difference
    t_stat, p_value_mean = sp_stats.ttest_ind(weekend_returns, weekday_returns, equal_var=False)

    # Test volatility difference (Levene's test for equal variances)
    _, p_value_vol = sp_stats.levene(weekend_returns, weekday_returns)

    vol_ratio = float(weekend_returns.std() / weekday_returns.std())

    if p_value_vol < 0.05 and vol_ratio < 0.85:
        # Significantly lower weekend vol → vol-scaled position sizing opportunity
        signals.append(Signal(
            description=f"Weekend vol compression: weekend std={weekend_returns.std()*100:.2f}% vs "
                        f"weekday {weekday_returns.std()*100:.2f}% (ratio={vol_ratio:.2f}, p={p_value_vol:.4f})",
            method="weekend_vol_compression",
            strength=min(1.0, (1.0 - vol_ratio) / 0.4),
            symbol="", timeframe="",
            metadata={
                "weekend_vol": float(weekend_returns.std()),
                "weekday_vol": float(weekday_returns.std()),
                "vol_ratio": vol_ratio,
                "p_value": float(p_value_vol),
            },
        ))

    return signals


def detect_us_session_effect(prices: pd.Series) -> list[Signal]:
    """Detect US trading session effect (UTC 13:00-21:00).

    Mechanism: peak liquidity from US institutional/ETF flows. Most
    significant moves happen during this window. Asia session (00:00-08:00)
    typically lower vol and often reverses overnight US moves.
    """
    signals = []
    if len(prices) < 200:
        return signals

    returns = prices.pct_change().dropna()
    hour = returns.index.hour
    us_session_mask = (hour >= 13) & (hour < 21)

    us_returns = returns[us_session_mask]
    other_returns = returns[~us_session_mask]

    if len(us_returns) < 100 or len(other_returns) < 100:
        return signals

    # Volatility comparison
    _, p_value_vol = sp_stats.levene(us_returns, other_returns)
    vol_ratio = float(us_returns.std() / other_returns.std())

    if p_value_vol < 0.05 and vol_ratio > 1.15:
        signals.append(Signal(
            description=f"US session vol amplification: US std={us_returns.std()*100:.2f}% vs "
                        f"other {other_returns.std()*100:.2f}% (ratio={vol_ratio:.2f}, p={p_value_vol:.4f})",
            method="us_session_vol",
            strength=min(1.0, (vol_ratio - 1.0) / 0.5),
            symbol="", timeframe="",
            metadata={
                "us_vol": float(us_returns.std()),
                "other_vol": float(other_returns.std()),
                "vol_ratio": vol_ratio,
                "p_value": float(p_value_vol),
            },
        ))

    return signals


def scan_calendar(prices: pd.Series) -> list[Signal]:
    """Run all calendar effect detectors."""
    signals = []
    signals.extend(detect_end_of_month(prices))
    signals.extend(detect_weekend_effect(prices))
    signals.extend(detect_us_session_effect(prices))
    return signals
