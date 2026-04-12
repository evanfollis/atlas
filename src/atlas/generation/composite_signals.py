"""Composite signal detectors — multi-source causal pattern recognition.

Unlike single-source signals that look for statistical anomalies in one series,
composite signals detect *structural conditions* across multiple data sources
that have a hypothesized causal mechanism. The mechanism matters: it tells us
when the signal should work and when it shouldn't.

Design principle: trade rarely, with high conviction. Each composite signal
should fire 5-20 times per year, not hundreds of times.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from atlas.generation.signals import Signal


def detect_fear_capitulation(
    prices: pd.Series,
    fear_greed: pd.Series,
    threshold_low: int = 25,
    threshold_high: int = 75,
    holding_period: int = 20,
) -> list[Signal]:
    """Detect capitulation buying opportunities using sentiment extremes.

    Mechanism: Extreme fear (< 15) reflects retail panic selling. When combined
    with price drawdown > 20% from recent high, it marks capitulation — forced
    sellers exhausted, risk/reward skews positive. We hold for `holding_period`
    bars after entry rather than flipping on every bar.

    Conversely, extreme greed (> 80) with price > 20% above recent low marks
    euphoria — overleveraged longs vulnerable to cascade.
    """
    signals = []
    if len(prices) < 100 or len(fear_greed) < 50:
        return signals

    # Align
    common = prices.index.intersection(fear_greed.index)
    if len(common) < 50:
        # Try forward-fill alignment for different frequencies
        fg_aligned = fear_greed.reindex(prices.index, method="ffill").dropna()
        if len(fg_aligned) < 50:
            return signals
        common = fg_aligned.index
        fg = fg_aligned
        px = prices.loc[common]
    else:
        fg = fear_greed.loc[common]
        px = prices.loc[common]

    # Price context: drawdown from rolling 60-bar high / rally from rolling 60-bar low
    rolling_high = px.rolling(60).max()
    rolling_low = px.rolling(60).min()
    drawdown = (px - rolling_high) / rolling_high
    rally = (px - rolling_low) / rolling_low

    # Count events
    fear_events = ((fg < threshold_low) & (drawdown < -0.10)).sum()
    greed_events = ((fg > threshold_high) & (rally > 0.15)).sum()

    if fear_events >= 3:
        # Test: what happens after fear capitulation?
        fear_mask = (fg < threshold_low) & (drawdown < -0.10)
        forward_returns = []
        for idx in fg.index[fear_mask]:
            pos = px.index.get_loc(idx)
            if pos + holding_period < len(px):
                fwd = (px.iloc[pos + holding_period] / px.iloc[pos]) - 1
                forward_returns.append(fwd)

        if len(forward_returns) >= 3:
            mean_fwd = float(np.mean(forward_returns))
            win_rate = float(np.mean([r > 0 for r in forward_returns]))
            signals.append(Signal(
                description=f"Fear capitulation: {fear_events} events, {win_rate:.0%} win rate, "
                            f"mean forward return {mean_fwd:.1%} over {holding_period} bars",
                method="fear_capitulation",
                strength=min(1.0, win_rate),
                symbol="", timeframe="",
                metadata={
                    "n_events": int(fear_events),
                    "win_rate": win_rate,
                    "mean_forward_return": mean_fwd,
                    "holding_period": holding_period,
                    "fear_threshold": threshold_low,
                    "drawdown_threshold": -0.15,
                },
            ))

    if greed_events >= 3:
        greed_mask = (fg > threshold_high) & (rally > 0.15)
        forward_returns = []
        for idx in fg.index[greed_mask]:
            pos = px.index.get_loc(idx)
            if pos + holding_period < len(px):
                fwd = (px.iloc[pos + holding_period] / px.iloc[pos]) - 1
                forward_returns.append(fwd)

        if len(forward_returns) >= 3:
            mean_fwd = float(np.mean(forward_returns))
            win_rate = float(np.mean([r < 0 for r in forward_returns]))
            signals.append(Signal(
                description=f"Greed euphoria: {greed_events} events, {win_rate:.0%} reversal rate, "
                            f"mean forward return {mean_fwd:.1%} over {holding_period} bars",
                method="greed_euphoria",
                strength=min(1.0, win_rate),
                symbol="", timeframe="",
                metadata={
                    "n_events": int(greed_events),
                    "reversal_rate": win_rate,
                    "mean_forward_return": mean_fwd,
                    "holding_period": holding_period,
                    "greed_threshold": threshold_high,
                    "rally_threshold": 0.20,
                },
            ))

    return signals


def detect_onchain_divergence(
    prices: pd.Series,
    onchain_volume: pd.Series,
    window: int = 20,
) -> list[Signal]:
    """Detect divergence between price and on-chain transaction volume.

    Mechanism: Rising price + declining on-chain volume → speculative rally
    without real economic activity. The price is driven by derivatives/leverage,
    not actual BTC movement. These rallies are fragile.

    Falling price + rising on-chain volume → large holders accumulating.
    Real economic activity increasing despite price decline signals informed
    buying (distribution to strong hands).
    """
    signals = []
    if len(prices) < 100 or len(onchain_volume) < 50:
        return signals

    vol_aligned = onchain_volume.reindex(prices.index, method="ffill").dropna()
    common = prices.index.intersection(vol_aligned.index)
    if len(common) < 100:
        return signals

    px = prices.loc[common]
    ov = vol_aligned.loc[common]

    # Rolling trends
    px_trend = px.pct_change(window).dropna()
    ov_trend = ov.pct_change(window).dropna()
    common2 = px_trend.index.intersection(ov_trend.index)
    px_trend = px_trend.loc[common2]
    ov_trend = ov_trend.loc[common2]

    # Bearish divergence: price up > 10%, on-chain volume down > 10%
    bearish_div = (px_trend > 0.10) & (ov_trend < -0.10)
    n_bearish = int(bearish_div.sum())

    # Bullish divergence: price down > 10%, on-chain volume up > 10%
    bullish_div = (px_trend < -0.10) & (ov_trend > 0.10)
    n_bullish = int(bullish_div.sum())

    holding = window  # hold for same window as measurement

    if n_bearish >= 3:
        fwd_returns = []
        for idx in px_trend.index[bearish_div]:
            pos = px.index.get_loc(idx)
            if pos + holding < len(px):
                fwd_returns.append(float(px.iloc[pos + holding] / px.iloc[pos] - 1))
        if len(fwd_returns) >= 3:
            mean_fwd = float(np.mean(fwd_returns))
            signals.append(Signal(
                description=f"Bearish on-chain divergence: {n_bearish} events, mean fwd return {mean_fwd:.1%}",
                method="onchain_divergence",
                strength=min(1.0, n_bearish / 20),
                symbol="", timeframe="",
                metadata={
                    "direction": "bearish", "n_events": n_bearish,
                    "mean_forward_return": mean_fwd, "window": window,
                    "holding_period": holding,
                },
            ))

    if n_bullish >= 3:
        fwd_returns = []
        for idx in px_trend.index[bullish_div]:
            pos = px.index.get_loc(idx)
            if pos + holding < len(px):
                fwd_returns.append(float(px.iloc[pos + holding] / px.iloc[pos] - 1))
        if len(fwd_returns) >= 3:
            mean_fwd = float(np.mean(fwd_returns))
            signals.append(Signal(
                description=f"Bullish on-chain divergence: {n_bullish} events, mean fwd return {mean_fwd:.1%}",
                method="onchain_divergence",
                strength=min(1.0, n_bullish / 20),
                symbol="", timeframe="",
                metadata={
                    "direction": "bullish", "n_events": n_bullish,
                    "mean_forward_return": mean_fwd, "window": window,
                    "holding_period": holding,
                },
            ))

    return signals


def detect_miner_capitulation(
    prices: pd.Series,
    hashrate: pd.Series,
    window: int = 30,
) -> list[Signal]:
    """Detect miner capitulation and recovery.

    Mechanism: When hashrate drops significantly (> 10% from recent peak),
    unprofitable miners are shutting down. They must sell BTC reserves to
    cover fixed costs → selling pressure. When hashrate recovers after a
    drop, capitulation is over — forced selling exhausted, price floor found.

    The buy signal is hashrate *recovery* (not the drop itself), because
    the drop causes selling and the recovery means that selling is done.
    """
    signals = []
    if len(prices) < 100 or len(hashrate) < 50:
        return signals

    hr_aligned = hashrate.reindex(prices.index, method="ffill").dropna()
    common = prices.index.intersection(hr_aligned.index)
    if len(common) < 100:
        return signals

    px = prices.loc[common]
    hr = hr_aligned.loc[common]

    # Hashrate drawdown from rolling peak
    hr_peak = hr.rolling(window).max()
    hr_drawdown = (hr - hr_peak) / hr_peak

    # Recovery: hashrate was down > 10% within last 2*window bars, now recovering
    was_down = hr_drawdown.rolling(window).min() < -0.10
    recovering = hr_drawdown > -0.03  # back within 3% of peak
    recovery_signal = was_down & recovering

    # Shift to avoid detecting the same recovery multiple times
    # Only count first recovery after each capitulation
    recovery_events = recovery_signal & (~recovery_signal.shift(1).fillna(False))
    n_events = int(recovery_events.sum())

    if n_events >= 3:
        holding = window
        fwd_returns = []
        for idx in hr.index[recovery_events]:
            pos = px.index.get_loc(idx)
            if pos + holding < len(px):
                fwd_returns.append(float(px.iloc[pos + holding] / px.iloc[pos] - 1))

        if len(fwd_returns) >= 3:
            mean_fwd = float(np.mean(fwd_returns))
            win_rate = float(np.mean([r > 0 for r in fwd_returns]))
            signals.append(Signal(
                description=f"Miner capitulation recovery: {n_events} events, "
                            f"{win_rate:.0%} win rate, mean fwd {mean_fwd:.1%}",
                method="miner_capitulation",
                strength=min(1.0, win_rate),
                symbol="", timeframe="",
                metadata={
                    "n_events": n_events, "win_rate": win_rate,
                    "mean_forward_return": mean_fwd, "window": window,
                    "holding_period": holding,
                },
            ))

    return signals


def detect_sentiment_regime_confluence(
    prices: pd.Series,
    fear_greed: pd.Series,
    onchain_volume: pd.Series,
    window: int = 20,
) -> list[Signal]:
    """Detect multi-source regime confluence — the highest-conviction signal.

    Mechanism: When ALL of these align, the causal narrative is coherent:
    - Extreme fear (sentiment) → retail has capitulated
    - On-chain volume rising → large holders are accumulating
    - Price below 60-bar low → drawdown provides entry

    This is the "smart money buying blood" pattern. The three sources
    triangulate the same story through different causal channels.
    Conversely, greed + falling on-chain + new highs = fragile top.
    """
    signals = []
    if len(prices) < 100:
        return signals

    fg_aligned = fear_greed.reindex(prices.index, method="ffill").dropna()
    ov_aligned = onchain_volume.reindex(prices.index, method="ffill").dropna()
    common = prices.index.intersection(fg_aligned.index).intersection(ov_aligned.index)
    if len(common) < 100:
        return signals

    px = prices.loc[common]
    fg = fg_aligned.loc[common]
    ov = ov_aligned.loc[common]

    ov_trend = ov.pct_change(window)
    px_low = px.rolling(60).min()
    px_high = px.rolling(60).max()

    # Bullish confluence: fear + accumulation + drawdown
    bull_signal = (fg < 25) & (ov_trend > 0.05) & (px <= px_low * 1.05)
    # Only first bar of each cluster
    bull_entry = bull_signal & (~bull_signal.shift(1).fillna(False))
    n_bull = int(bull_entry.sum())

    # Bearish confluence: greed + distribution + extended rally
    bear_signal = (fg > 75) & (ov_trend < -0.05) & (px >= px_high * 0.95)
    bear_entry = bear_signal & (~bear_signal.shift(1).fillna(False))
    n_bear = int(bear_entry.sum())

    holding = 30  # 30-bar hold for regime trades

    if n_bull >= 2:
        fwd_returns = []
        for idx in px.index[bull_entry]:
            pos = px.index.get_loc(idx)
            if pos + holding < len(px):
                fwd_returns.append(float(px.iloc[pos + holding] / px.iloc[pos] - 1))
        if len(fwd_returns) >= 2:
            mean_fwd = float(np.mean(fwd_returns))
            win_rate = float(np.mean([r > 0 for r in fwd_returns]))
            signals.append(Signal(
                description=f"Bullish confluence (fear+accumulation+drawdown): {n_bull} events, "
                            f"{win_rate:.0%} win rate, mean fwd {mean_fwd:.1%}",
                method="sentiment_regime_confluence",
                strength=min(1.0, win_rate),
                symbol="", timeframe="",
                metadata={
                    "direction": "bullish", "n_events": n_bull,
                    "win_rate": win_rate, "mean_forward_return": mean_fwd,
                    "holding_period": holding,
                    "components": ["fear_greed<25", "onchain_vol_rising", "near_60bar_low"],
                },
            ))

    if n_bear >= 2:
        fwd_returns = []
        for idx in px.index[bear_entry]:
            pos = px.index.get_loc(idx)
            if pos + holding < len(px):
                fwd_returns.append(float(px.iloc[pos + holding] / px.iloc[pos] - 1))
        if len(fwd_returns) >= 2:
            mean_fwd = float(np.mean(fwd_returns))
            win_rate = float(np.mean([r < 0 for r in fwd_returns]))
            signals.append(Signal(
                description=f"Bearish confluence (greed+distribution+rally): {n_bear} events, "
                            f"{win_rate:.0%} reversal rate, mean fwd {mean_fwd:.1%}",
                method="sentiment_regime_confluence",
                strength=min(1.0, win_rate),
                symbol="", timeframe="",
                metadata={
                    "direction": "bearish", "n_events": n_bear,
                    "reversal_rate": win_rate, "mean_forward_return": mean_fwd,
                    "holding_period": holding,
                    "components": ["fear_greed>75", "onchain_vol_falling", "near_60bar_high"],
                },
            ))

    return signals


def scan_composite(
    prices: pd.Series,
    alt_data: dict[str, pd.DataFrame],
) -> list[Signal]:
    """Run all composite signal detectors.

    Args:
        prices: Close price series from OHLCV data.
        alt_data: Dict from AlternativeData.fetch_all().
    """
    signals = []

    fg = alt_data.get("fear_greed")
    ov = alt_data.get("onchain_volume")
    hr = alt_data.get("hashrate")

    if fg is not None and "fear_greed" in fg.columns:
        fg_series = fg["fear_greed"]
        signals.extend(detect_fear_capitulation(prices, fg_series))

        if ov is not None and "onchain_volume_usd" in ov.columns:
            signals.extend(detect_sentiment_regime_confluence(
                prices, fg_series, ov["onchain_volume_usd"],
            ))

    if ov is not None and "onchain_volume_usd" in ov.columns:
        signals.extend(detect_onchain_divergence(prices, ov["onchain_volume_usd"]))

    if hr is not None and "hashrate" in hr.columns:
        signals.extend(detect_miner_capitulation(prices, hr["hashrate"]))

    return signals
