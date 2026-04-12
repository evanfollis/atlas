"""Vectorized backtesting — signal series to return metrics."""

import inspect
from dataclasses import dataclass, field

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
    fee_bps: float = 0,
) -> BacktestResult:
    """Run a vectorized backtest.

    Args:
        prices: Price series (e.g. close prices)
        signals: Signal series aligned to prices. Values: 1 (long), -1 (short), 0 (flat)
        periods_per_year: For annualization. 365*6 = 4h candles.
        fee_bps: One-way fee in basis points, charged on each position change.
            A round trip (enter + exit) costs 2 * fee_bps total.
            Kraken taker fee is ~26 bps → pass 26.
    """
    returns = prices.pct_change().dropna()
    signals_aligned = signals.reindex(returns.index).fillna(0).shift(1).dropna()
    returns = returns.reindex(signals_aligned.index)

    strategy_returns = returns * signals_aligned

    # Deduct trading costs on position changes
    if fee_bps > 0:
        position_diff = signals_aligned.diff()
        # First bar: entering from flat (0), so any non-zero position is a trade
        position_diff.iloc[0] = signals_aligned.iloc[0]
        position_changed = position_diff != 0
        cost_per_trade = fee_bps / 10_000  # one-way fee per position change
        strategy_returns = strategy_returns.copy()
        strategy_returns[position_changed] -= cost_per_trade

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


@dataclass
class WalkForwardResult:
    """Aggregated result from walk-forward validation across multiple folds."""
    folds: list[dict]  # Per-fold: {train_size, test_size, oos_sharpe, ...}
    oos_returns: pd.Series  # Concatenated OOS returns across all folds
    mean_oos_sharpe: float  # Average of per-fold Sharpes (for diagnostics)
    aggregate_oos_sharpe: float  # Sharpe computed on concatenated returns (for decisions)
    n_folds: int


def walk_forward_backtest(
    df: pd.DataFrame,
    signal_builder: callable,
    n_folds: int = 5,
    train_ratio: float = 0.7,
    periods_per_year: float = 365 * 6,
    fee_bps: float = 0,
) -> WalkForwardResult:
    """Anchored walk-forward evaluation: expanding pre-test window, sliding test window.

    Splits data into n_folds sequential test blocks. For each fold, the pre-test
    window is all data up to that fold's test block (expanding). Only test-block
    signals are evaluated.

    The signal_builder may be either stateless or trainable:
      - Stateless (1-arg): called as `signal_builder(test_df)`. Caller is
        responsible for using only past-anchored rolling windows inside.
      - Trainable (2-arg): called as `signal_builder(train_df, test_df)`.
        Caller may fit any state on train_df and apply it to test_df. Arity
        is detected automatically; the 2-arg form is opt-in.

    Args:
        df: OHLCV DataFrame with at least a 'close' column.
        signal_builder: Callable(test_df) -> pd.Series OR
            Callable(train_df, test_df) -> pd.Series. Trainable form receives
            the expanding train window for each fold and may fit state.
        n_folds: Number of walk-forward folds.
        train_ratio: Fraction of total data reserved as the initial pre-test window.
            The remaining (1 - train_ratio) is divided into n_folds test blocks.
        periods_per_year: For annualization.
        fee_bps: Trading fee in basis points.

    Returns:
        WalkForwardResult with per-fold details and concatenated OOS returns.
    """
    n = len(df)
    initial_train_end = int(n * train_ratio)
    test_region = n - initial_train_end
    fold_size = test_region // n_folds

    if fold_size < 50:
        raise ValueError(f"Insufficient data for {n_folds} folds: only {fold_size} bars per fold (need ≥50 for signal warm-up)")

    # Detect signal_builder arity: 1-arg = stateless (test only),
    # 2-arg = trainable (train_df, test_df). Opt-in extension so existing
    # stateless callers continue to work unchanged.
    try:
        sig = inspect.signature(signal_builder)
        n_params = sum(
            1 for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                          inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and p.default is inspect.Parameter.empty
        )
        trainable = n_params >= 2
    except (TypeError, ValueError):
        trainable = False

    folds = []
    all_oos_returns = []

    for i in range(n_folds):
        test_start = initial_train_end + i * fold_size
        test_end = initial_train_end + (i + 1) * fold_size if i < n_folds - 1 else n

        train_df = df.iloc[:test_start]
        test_df = df.iloc[test_start:test_end]

        test_signals = (signal_builder(train_df, test_df) if trainable
                        else signal_builder(test_df))
        oos_result = run_backtest(test_df["close"], test_signals, periods_per_year=periods_per_year, fee_bps=fee_bps)

        folds.append({
            "fold": i,
            "train_size": len(train_df),
            "test_size": len(test_df),
            "oos_sharpe": oos_result.sharpe_ratio,
            "oos_total_return": oos_result.total_return,
            "oos_max_drawdown": oos_result.max_drawdown,
        })
        all_oos_returns.append(oos_result.returns)

    oos_returns = pd.concat(all_oos_returns, ignore_index=True)
    mean_oos_sharpe = float(np.mean([f["oos_sharpe"] for f in folds]))

    # Aggregate Sharpe from concatenated OOS returns — consistent with statistical tests
    oos_std = oos_returns.std()
    aggregate_oos_sharpe = float(oos_returns.mean() / oos_std * np.sqrt(periods_per_year)) if oos_std > 0 else 0.0

    return WalkForwardResult(
        folds=folds,
        oos_returns=oos_returns,
        mean_oos_sharpe=mean_oos_sharpe,
        aggregate_oos_sharpe=aggregate_oos_sharpe,
        n_folds=n_folds,
    )
