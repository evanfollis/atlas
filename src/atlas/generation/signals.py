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
    """Detect volatility regime changes using rolling std ratio."""
    signals = []
    if len(prices) < window * 2:
        return signals

    vol_short = prices.pct_change().rolling(window // 2).std()
    vol_long = prices.pct_change().rolling(window).std()
    ratio = (vol_short / vol_long).dropna()

    if len(ratio) == 0:
        return signals

    latest = ratio.iloc[-1]
    if latest > 2.0:
        signals.append(Signal(
            description=f"Volatility expansion: short/long vol ratio = {latest:.2f}",
            method="rolling_vol_ratio",
            strength=min(1.0, (latest - 1.5) / 2.0),
            symbol="",
            timeframe="",
            metadata={"vol_ratio": float(latest), "window": window},
        ))
    elif latest < 0.5:
        signals.append(Signal(
            description=f"Volatility compression: short/long vol ratio = {latest:.2f}",
            method="rolling_vol_ratio",
            strength=min(1.0, (0.8 - latest) / 0.8),
            symbol="",
            timeframe="",
            metadata={"vol_ratio": float(latest), "window": window},
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
    """Detect mean-reversion signals via z-score of price vs moving average."""
    signals = []
    if windows is None:
        windows = [20, 50, 100]

    for w in windows:
        if len(prices) < w + 10:
            continue
        ma = prices.rolling(w).mean()
        std = prices.rolling(w).std()
        z = ((prices - ma) / std).dropna()
        if len(z) == 0:
            continue

        latest_z = z.iloc[-1]
        if abs(latest_z) > 2.0:
            direction = "below" if latest_z < 0 else "above"
            signals.append(Signal(
                description=f"Price {abs(latest_z):.1f}σ {direction} {w}-period MA",
                method="zscore_mean_reversion",
                strength=min(1.0, (abs(latest_z) - 1.5) / 2.0),
                symbol="",
                timeframe="",
                metadata={"window": w, "zscore": float(latest_z)},
            ))

    return signals


def detect_volume_anomaly(df: pd.DataFrame, window: int = 20) -> list[Signal]:
    """Detect unusual volume relative to recent history."""
    signals = []
    if len(df) < window + 5 or "volume" not in df.columns:
        return signals

    vol_ma = df["volume"].rolling(window).mean()
    vol_std = df["volume"].rolling(window).std()
    z = ((df["volume"] - vol_ma) / vol_std).dropna()

    if len(z) == 0:
        return signals

    latest = z.iloc[-1]
    if latest > 3.0:
        signals.append(Signal(
            description=f"Volume spike: {latest:.1f}σ above {window}-period average",
            method="volume_zscore",
            strength=min(1.0, (latest - 2.0) / 3.0),
            symbol="",
            timeframe="",
            metadata={"volume_zscore": float(latest), "window": window},
        ))

    return signals


def scan_all(df: pd.DataFrame) -> list[Signal]:
    """Run all signal detectors on a price DataFrame."""
    signals = []
    prices = df["close"]
    returns = prices.pct_change().dropna()

    signals.extend(detect_regime_change(prices))
    signals.extend(detect_autocorrelation(returns))
    signals.extend(detect_mean_reversion(prices))
    signals.extend(detect_volume_anomaly(df))

    return signals
