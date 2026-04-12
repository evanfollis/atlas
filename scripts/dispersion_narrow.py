"""Phase C2: Narrow dispersion retest — BitMEX + KrakenFutures only, 8h cadence.

Pre-registered design (see backlog C2, memory phase_b2_pattern.md):
  - Venue membership frozen to {BitMEX, KrakenFutures}. OKX excluded because
    its history only starts 2026-01-08 and including it made the prior
    dispersion test have time-varying statistical meaning.
  - Settlement cadence: 8h bars aligned to 00/08/16 UTC. Kraken funding is
    hourly; resample by last-observation in each 8h window.
  - Dispersion = |fund_bitmex - fund_kraken| at each 8h timestamp.
  - Residualize dispersion against mean funding via OLS on the IS sample,
    apply the IS-fit residualization to OOS (no leakage).
  - Test: forward 8h & 24h returns regressed on interaction
    mean_fund * z(disp_resid), where z() uses IS mean/std.
  - IS/OOS split: first 70% of aligned timestamps IS.
  - Reject null at |t|>1.96 on OOS interaction coefficient AND sign matches IS.

Hypothesis (why this differs from prior 3 B2-template nulls, per memory rule):
  - Multi-variable conditioning (interaction, not single-var extreme).
  - Sub-daily horizon (8h primary, 24h secondary).
  - Residualized — isolates dispersion information orthogonal to mean funding,
    which alone already carries the known reversal signal.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.data.derivatives import DerivativesData
from atlas.data.market import MarketData


CACHE = Path("data")
dd = DerivativesData(cache_dir=CACHE / "derivs")
md = MarketData(cache_dir=CACHE)

bmx = dd.fetch_funding_rates("bitmex", "BTC")["fundingRate"]
krk = dd.fetch_funding_rates("krakenfutures", "BTC")["fundingRate"]
bmx.index = pd.to_datetime(bmx.index, utc=True)
krk.index = pd.to_datetime(krk.index, utc=True)
print(f"bitmex funding: n={len(bmx)} {bmx.index[0]} → {bmx.index[-1]}")
print(f"kraken funding: n={len(krk)} {krk.index[0]} → {krk.index[-1]}")

# Build 8h grid over the overlap window.
start = max(bmx.index.min(), krk.index.min()).ceil("8h")
end = min(bmx.index.max(), krk.index.max()).floor("8h")
grid = pd.date_range(start, end, freq="8h", tz="UTC")
print(f"8h grid: n={len(grid)} {grid[0]} → {grid[-1]}")

# For each 8h timestamp t, take the last observation ≤ t (no lookahead).
def last_obs(series: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    return series.reindex(series.index.union(idx)).ffill().reindex(idx)

bmx_8h = last_obs(bmx, grid)
krk_8h = last_obs(krk, grid)
df = pd.DataFrame({"bmx": bmx_8h, "krk": krk_8h}).dropna()
df["mean_fund"] = 0.5 * (df["bmx"] + df["krk"])
df["disp"] = (df["bmx"] - df["krk"]).abs()
print(f"aligned rows: {len(df)}")

# Forward returns from 4h BTC/USDT — take two bars forward for 8h, six for 24h.
btc = md.fetch_ohlcv("BTC/USDT", "4h", since="2025-01-01")
btc.index = pd.to_datetime(btc.index, utc=True)
p = btc["close"]
# align to nearest 4h
def fwd_log_return(p: pd.Series, idx: pd.DatetimeIndex, horizon_bars: int) -> pd.Series:
    # p is 4h; find the bar at/after t, then horizon_bars ahead
    p_sorted = p.sort_index()
    entry_idx = p_sorted.index.searchsorted(idx, side="left")
    out = np.full(len(idx), np.nan)
    for i, ei in enumerate(entry_idx):
        if ei + horizon_bars >= len(p_sorted) or ei >= len(p_sorted):
            continue
        p0 = p_sorted.iloc[ei]
        p1 = p_sorted.iloc[ei + horizon_bars]
        if p0 > 0 and p1 > 0:
            out[i] = np.log(p1 / p0)
    return pd.Series(out, index=idx)

df["fwd_8h"] = fwd_log_return(p, df.index, 2)
df["fwd_24h"] = fwd_log_return(p, df.index, 6)
df = df.dropna(subset=["fwd_8h", "fwd_24h"])
print(f"with forward returns: {len(df)}")

# IS/OOS split.
split_i = int(len(df) * 0.70)
is_df = df.iloc[:split_i].copy()
oos_df = df.iloc[split_i:].copy()
print(f"IS n={len(is_df)} OOS n={len(oos_df)} split={df.index[split_i]}")

# Residualize disp against mean_fund on IS only; apply fit to OOS.
from numpy.linalg import lstsq
X_is = np.column_stack([np.ones(len(is_df)), is_df["mean_fund"].values])
beta, *_ = lstsq(X_is, is_df["disp"].values, rcond=None)
a, b = beta
def resid(d: pd.DataFrame) -> np.ndarray:
    return d["disp"].values - (a + b * d["mean_fund"].values)
is_df["disp_resid"] = resid(is_df)
oos_df["disp_resid"] = resid(oos_df)
print(f"IS residualization: disp = {a:.3e} + {b:.3e} * mean_fund")

# z-score disp_resid using IS stats only.
z_mu, z_sd = is_df["disp_resid"].mean(), is_df["disp_resid"].std()
is_df["z_disp"] = (is_df["disp_resid"] - z_mu) / z_sd
oos_df["z_disp"] = (oos_df["disp_resid"] - z_mu) / z_sd

# Standardize mean_fund similarly (IS stats).
m_mu, m_sd = is_df["mean_fund"].mean(), is_df["mean_fund"].std()
is_df["z_mf"] = (is_df["mean_fund"] - m_mu) / m_sd
oos_df["z_mf"] = (oos_df["mean_fund"] - m_mu) / m_sd

def regress(d: pd.DataFrame, y_col: str) -> dict:
    X = np.column_stack([np.ones(len(d)), d["z_mf"].values, d["z_disp"].values,
                         (d["z_mf"] * d["z_disp"]).values])
    y = d[y_col].values
    beta, *_ = lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    sigma2 = (resid ** 2).sum() / (n - k)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    t = beta / se
    return {"beta": beta, "se": se, "t": t, "n": n}

print("\n=== IS ===")
for horizon in ["fwd_8h", "fwd_24h"]:
    r = regress(is_df, horizon)
    names = ["const", "z_mf", "z_disp", "z_mf*z_disp"]
    print(f"{horizon}: n={r['n']}")
    for name, b_, se_, t_ in zip(names, r["beta"], r["se"], r["t"]):
        print(f"  {name:14s} beta={b_:+.5f} se={se_:.5f} t={t_:+.2f}")

print("\n=== OOS ===")
for horizon in ["fwd_8h", "fwd_24h"]:
    r = regress(oos_df, horizon)
    names = ["const", "z_mf", "z_disp", "z_mf*z_disp"]
    print(f"{horizon}: n={r['n']}")
    for name, b_, se_, t_ in zip(names, r["beta"], r["se"], r["t"]):
        print(f"  {name:14s} beta={b_:+.5f} se={se_:.5f} t={t_:+.2f}")
