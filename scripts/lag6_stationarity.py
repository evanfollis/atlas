"""Apply rolling stationarity tooling to lag-6 BTC→ETH finding.

Replaces the calendar-year table in findings/2026-04-12_lag6_decay.md with
rolling-β + rolling-correlation + CUSUM and Chow tests.
"""
from pathlib import Path
import numpy as np
import pandas as pd

from atlas.data.market import MarketData
from atlas.analysis.stationarity import (
    rolling_correlation, rolling_ols, cusum_ols, chow_test,
)

md = MarketData(cache_dir=Path("data"))
btc = md.fetch_ohlcv("BTC/USDT", "4h", since="2017-01-01")
eth = md.fetch_ohlcv("ETH/USDT", "4h", since="2017-01-01")

btc_ret = btc["close"].pct_change()
eth_ret = eth["close"].pct_change()
common = btc_ret.index.intersection(eth_ret.index)
x = btc_ret.loc[common].shift(6)  # lag-6 BTC return
y = eth_ret.loc[common]
df = pd.concat([x.rename("btc_lag6"), y.rename("eth")], axis=1).dropna()
print(f"Aligned obs: {len(df)} from {df.index[0]} to {df.index[-1]}")

# Rolling correlation, window = 90 days = 540 4h bars
W = 540
rc = rolling_correlation(df["btc_lag6"], df["eth"], window=W)
r_valid = rc["r"].dropna()
print(f"\nRolling 90d r: mean={r_valid.mean():.3f} min={r_valid.min():.3f} "
      f"max={r_valid.max():.3f} frac<0={(r_valid<0).mean():.2%}")

# Rolling OLS β
ro = rolling_ols(df["btc_lag6"], df["eth"], window=W)
b = ro["beta"].dropna()
print(f"Rolling 90d β: mean={b.mean():.4f} first-year-avg={b.iloc[:2190].mean():.4f} "
      f"last-year-avg={b.iloc[-2190:].mean():.4f}")

# CUSUM for structural stability across full sample
cr = cusum_ols(df["eth"].values, df["btc_lag6"].values, alpha=0.05)
print(f"\nCUSUM: stat={cr.statistic:.2f} crit={cr.critical_value:.2f} "
      f"reject_stable={cr.reject_stable} "
      f"first_breach_idx={cr.first_breach_index}")
if cr.first_breach_index is not None:
    ts = df.index[cr.first_breach_index]
    print(f"  First breach timestamp: {ts}")

# Chow test at ~2021 boundary (halfway through, matches where per-year r flipped)
break_idx = len(df) // 2
ch = chow_test(df["eth"].values, df["btc_lag6"].values, break_index=break_idx)
print(f"\nChow @ mid-sample ({df.index[break_idx]}): "
      f"F={ch.f_statistic:.2f} p={ch.p_value:.4f} reject={ch.reject_stable}")

# Chow test around Jan 2021 (visual inflection in calendar-year table)
target = pd.Timestamp("2021-01-01", tz="UTC")
idx_2021 = df.index.get_indexer([target], method="nearest")[0]
ch2 = chow_test(df["eth"].values, df["btc_lag6"].values, break_index=int(idx_2021))
print(f"Chow @ 2021-01-01 (idx {idx_2021}): "
      f"F={ch2.f_statistic:.2f} p={ch2.p_value:.4f} reject={ch2.reject_stable}")
