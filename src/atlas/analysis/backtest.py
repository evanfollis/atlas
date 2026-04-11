"""Vectorized backtesting — signal series to return metrics."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    n_trades: int
    returns: pd.Series  # Per-period returns for statistical testing


def run_backtest(
    prices: pd.Series,
    signals: pd.Series,
    periods_per_year: float = 365 * 6,  # Default: 4h candles
) -> BacktestResult:
    """Run a vectorized backtest.

    Args:
        prices: Price series (e.g. close prices)
        signals: Signal series aligned to prices. Values: 1 (long), -1 (short), 0 (flat)
        periods_per_year: For annualization. 365*6 = 4h candles.
    """
    returns = prices.pct_change().dropna()
    signals_aligned = signals.reindex(returns.index).fillna(0).shift(1).dropna()
    returns = returns.reindex(signals_aligned.index)

    strategy_returns = returns * signals_aligned

    cumulative = (1 + strategy_returns).cumprod()
    total_return = float(cumulative.iloc[-1] - 1) if len(cumulative) > 0 else 0.0

    mean_ret = strategy_returns.mean()
    std_ret = strategy_returns.std()
    sharpe = float(mean_ret / std_ret * np.sqrt(periods_per_year)) if std_ret > 0 else 0.0

    annualized = float((1 + mean_ret) ** periods_per_year - 1)

    running_max = cumulative.cummax()
    drawdowns = (cumulative - running_max) / running_max
    max_drawdown = float(drawdowns.min())

    trade_returns = strategy_returns[signals_aligned != 0]
    n_trades = int((signals_aligned.diff().fillna(0) != 0).sum())
    win_rate = float((trade_returns > 0).mean()) if len(trade_returns) > 0 else 0.0

    return BacktestResult(
        total_return=total_return,
        annualized_return=annualized,
        sharpe_ratio=sharpe,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        n_trades=n_trades,
        returns=strategy_returns,
    )
