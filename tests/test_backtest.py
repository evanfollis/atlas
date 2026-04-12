"""Tests for vectorized backtest engine."""

import numpy as np
import pandas as pd
import pytest

from atlas.analysis.backtest import run_backtest, walk_forward_backtest


def _make_prices(returns: list[float]) -> pd.Series:
    """Build a price series from a list of returns."""
    prices = [100.0]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    return pd.Series(prices, name="close")


def test_constant_long_positive_returns() -> None:
    """Always long on a steadily rising asset → positive total return."""
    prices = _make_prices([0.01] * 100)
    signals = pd.Series(1, index=prices.index)
    result = run_backtest(prices, signals)
    assert result.total_return > 0


def test_constant_short_positive_returns() -> None:
    """Always short on a rising asset → negative total return."""
    prices = _make_prices([0.01] * 100)
    signals = pd.Series(-1, index=prices.index)
    result = run_backtest(prices, signals)
    assert result.total_return < 0


def test_flat_signal_zero_returns() -> None:
    """Signal = 0 → no exposure → zero returns."""
    prices = _make_prices([0.01] * 50)
    signals = pd.Series(0, index=prices.index)
    result = run_backtest(prices, signals)
    assert abs(result.total_return) < 1e-10


def test_sharpe_positive_for_good_strategy() -> None:
    """Strategy with consistent positive returns has positive Sharpe."""
    np.random.seed(42)
    returns = list(np.random.normal(0.002, 0.01, 200))
    prices = _make_prices(returns)
    signals = pd.Series(1, index=prices.index)
    result = run_backtest(prices, signals)
    assert result.sharpe_ratio > 0


def test_max_drawdown_is_negative() -> None:
    """Max drawdown should be <= 0."""
    prices = _make_prices([0.05, -0.10, 0.02, -0.08, 0.03])
    signals = pd.Series(1, index=prices.index)
    result = run_backtest(prices, signals)
    assert result.max_drawdown <= 0


def test_win_rate_bounds() -> None:
    """Win rate must be between 0 and 1."""
    prices = _make_prices([0.01, -0.01, 0.02, -0.02] * 25)
    signals = pd.Series(1, index=prices.index)
    result = run_backtest(prices, signals)
    assert 0 <= result.win_rate <= 1


def test_fees_reduce_returns() -> None:
    """Positive fee_bps should reduce total return vs zero fees."""
    prices = _make_prices([0.01] * 100)
    signals = pd.Series(1, index=prices.index)
    no_fee = run_backtest(prices, signals, fee_bps=0)
    with_fee = run_backtest(prices, signals, fee_bps=26)
    assert with_fee.total_return < no_fee.total_return


def test_fees_zero_on_no_position_change() -> None:
    """Constant position → fee only on first entry, not every bar."""
    prices = _make_prices([0.01] * 100)
    signals = pd.Series(1, index=prices.index)
    result = run_backtest(prices, signals, fee_bps=26)
    # Only 1 position change (0→1 at start), so cost is small
    no_fee = run_backtest(prices, signals, fee_bps=0)
    # Difference should be roughly one round-trip cost
    diff = no_fee.total_return - result.total_return
    assert 0 < diff < 0.02  # one round-trip of 52 bps


def test_fees_scale_with_trades() -> None:
    """More position changes → more fee drag."""
    prices = _make_prices([0.01] * 100)
    # Alternating signal: trade every bar
    signals = pd.Series([1 if i % 2 == 0 else -1 for i in range(len(prices))], index=prices.index)
    few_trades = run_backtest(prices, signals, fee_bps=10)
    # Constant signal: one trade
    const_signals = pd.Series(1, index=prices.index)
    one_trade = run_backtest(prices, const_signals, fee_bps=10)
    # Frequent trading should have more fee drag relative to no-fee
    few_no_fee = run_backtest(prices, signals, fee_bps=0)
    one_no_fee = run_backtest(prices, const_signals, fee_bps=0)
    drag_frequent = few_no_fee.total_return - few_trades.total_return
    drag_constant = one_no_fee.total_return - one_trade.total_return
    assert drag_frequent > drag_constant


def test_walk_forward_basic() -> None:
    """Walk-forward produces expected number of folds with OOS returns."""
    np.random.seed(42)
    prices = _make_prices(list(np.random.normal(0.001, 0.02, 1000)))
    df = pd.DataFrame({"close": prices})
    signal_builder = lambda sub_df: pd.Series(1, index=sub_df.index)
    result = walk_forward_backtest(df, signal_builder, n_folds=5)
    assert result.n_folds == 5
    assert len(result.folds) == 5
    assert len(result.oos_returns) > 0


def test_walk_forward_trainable_signal_builder() -> None:
    """2-arg signal_builder receives (train_df, test_df) and can carry fitted state."""
    np.random.seed(42)
    prices = _make_prices(list(np.random.normal(0.001, 0.02, 1000)))
    df = pd.DataFrame({"close": prices})
    train_sizes_seen: list[int] = []

    def trainable_builder(train_df: pd.DataFrame, test_df: pd.DataFrame) -> pd.Series:
        # Carry fitted state: mean of train returns → signal sign on test.
        train_mean = train_df["close"].pct_change().mean()
        train_sizes_seen.append(len(train_df))
        return pd.Series(1 if train_mean > 0 else -1, index=test_df.index)

    result = walk_forward_backtest(df, trainable_builder, n_folds=3)
    assert result.n_folds == 3
    # Train sizes grow across folds (expanding window)
    assert train_sizes_seen == sorted(train_sizes_seen)
    assert train_sizes_seen[0] < train_sizes_seen[-1]


def test_walk_forward_expanding_train() -> None:
    """Each fold's training set should be larger than the previous."""
    np.random.seed(42)
    prices = _make_prices(list(np.random.normal(0.001, 0.02, 1000)))
    df = pd.DataFrame({"close": prices})
    signal_builder = lambda sub_df: pd.Series(1, index=sub_df.index)
    result = walk_forward_backtest(df, signal_builder, n_folds=3)
    train_sizes = [f["train_size"] for f in result.folds]
    assert train_sizes == sorted(train_sizes)
    assert train_sizes[0] < train_sizes[-1]


def test_walk_forward_insufficient_data() -> None:
    """Too few bars for requested folds should raise ValueError."""
    prices = _make_prices([0.01] * 100)
    df = pd.DataFrame({"close": prices})
    signal_builder = lambda sub_df: pd.Series(1, index=sub_df.index)
    with pytest.raises(ValueError, match="Insufficient data"):
        walk_forward_backtest(df, signal_builder, n_folds=10)


def test_walk_forward_fees_applied() -> None:
    """Walk-forward with fees should produce lower returns than without."""
    np.random.seed(42)
    prices = _make_prices(list(np.random.normal(0.002, 0.01, 1000)))
    df = pd.DataFrame({"close": prices})
    signal_builder = lambda sub_df: pd.Series(1, index=sub_df.index)
    no_fee = walk_forward_backtest(df, signal_builder, n_folds=3, fee_bps=0)
    with_fee = walk_forward_backtest(df, signal_builder, n_folds=3, fee_bps=26)
    no_fee_total = float((1 + no_fee.oos_returns).prod() - 1)
    fee_total = float((1 + with_fee.oos_returns).prod() - 1)
    assert fee_total < no_fee_total


def test_signal_shift_no_lookahead() -> None:
    """Signals are shifted by 1 period — no lookahead bias.

    If signal[t] = 1, the strategy return at t comes from returns[t] * signal[t-1].
    So signal at last bar shouldn't affect last bar's strategy return.
    """
    prices = _make_prices([0.0] * 10 + [0.50])  # huge spike at end
    signals = pd.Series(0, index=prices.index)
    signals.iloc[-1] = 1  # signal fires on the spike bar itself
    result = run_backtest(prices, signals)
    # Should NOT capture the 50% move because signal is shifted
    assert result.total_return < 0.01
