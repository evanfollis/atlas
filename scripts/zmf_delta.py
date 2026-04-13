"""Funding-delta probe: does the CHANGE in mean funding (stock→flow) predict
forward BTC returns differently than the level?

Motivation. The level signal (`z_mf`) carries BTC 24h reversal (OOS t=-2.41).
Level is a stock measure of positioning. A delta is a flow measure — the
decision to add/cover in the last 8h window. Memory's stopping rule
explicitly flags "liquidation *flow* events, not positioning *stock* extremes"
as an unblocking dimension. The funding delta isn't a liquidation event but
it is the same stock→flow distinction applied to funding itself.

Pre-registered:
  - BitMEX+KrakenFutures mean funding on 8h grid (same as dispersion_narrow).
  - delta_mf(t) = mean_fund(t) - mean_fund(t-1). z-score on IS only.
  - Model A: fwd_24h ~ α + β·z_delta          (delta alone)
  - Model B: fwd_24h ~ α + β1·z_mf + β2·z_delta  (does delta add over level?)
  - IS = first 70%, OOS = last 30%.
  - Reject null (delta carries information): OOS |t|(β_delta in Model B) ≥ 1.96
    AND sign consistent IS→OOS.
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

start = max(bmx.index.min(), krk.index.min()).ceil("8h")
end = min(bmx.index.max(), krk.index.max()).floor("8h")
grid = pd.date_range(start, end, freq="8h", tz="UTC")

def last_obs(s, idx):
    return s.reindex(s.index.union(idx)).ffill().reindex(idx)

df = pd.DataFrame({"bmx": last_obs(bmx, grid), "krk": last_obs(krk, grid)}).dropna()
df["mean_fund"] = 0.5 * (df["bmx"] + df["krk"])
df["delta_mf"] = df["mean_fund"].diff()
df = df.dropna()

btc = md.fetch_ohlcv("BTC/USDT", "4h", since="2025-01-01")
btc.index = pd.to_datetime(btc.index, utc=True)
p = btc["close"].sort_index()
ei = p.index.searchsorted(df.index, side="left")
fwd = np.full(len(df), np.nan)
for i, e in enumerate(ei):
    if e + 6 < len(p) and e < len(p):
        p0, p1 = p.iloc[e], p.iloc[e + 6]
        if p0 > 0 and p1 > 0:
            fwd[i] = np.log(p1 / p0)
df["fwd_24h"] = fwd
df = df.dropna()
print(f"n={len(df)}")

split_i = int(len(df) * 0.70)
is_df, oos_df = df.iloc[:split_i].copy(), df.iloc[split_i:].copy()

for col in ["mean_fund", "delta_mf"]:
    mu, sd = is_df[col].mean(), is_df[col].std()
    is_df[f"z_{col}"] = (is_df[col] - mu) / sd
    oos_df[f"z_{col}"] = (oos_df[col] - mu) / sd

def reg(d, cols):
    X = np.column_stack([np.ones(len(d))] + [d[c].values for c in cols])
    y = d["fwd_24h"].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ beta
    n, k = X.shape
    sig2 = (r ** 2).sum() / (n - k)
    cov = sig2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    return beta, se, beta / se, n

for label, d in [("IS", is_df), ("OOS", oos_df)]:
    print(f"\n=== {label} ===")
    for name, cols in [("A: delta alone", ["z_delta_mf"]),
                       ("B: level+delta", ["z_mean_fund", "z_delta_mf"])]:
        b, se, t, n = reg(d, cols)
        print(f"{name} (n={n}):")
        terms = ["const"] + cols
        for nm, b_, se_, t_ in zip(terms, b, se, t):
            print(f"  {nm:14s} β={b_:+.5f} se={se_:.5f} t={t_:+.2f}")
