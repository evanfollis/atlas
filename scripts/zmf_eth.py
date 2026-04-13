"""Cross-asset robustness: does BitMEX+Kraken mean-funding reversal hold on ETH?

Pre-registered:
  - Same venue set (BitMEX, KrakenFutures), same 8h cadence, same horizons
    (fwd_8h, fwd_24h on ETH/USDT Kraken closes) as dispersion_narrow.py.
  - Model: fwd = α + β·z_mf  (no dispersion terms — this is the univariate
    baseline that replicated OOS at 24h on BTC).
  - IS/OOS: first 70% IS.
  - Reject null: OOS |t| ≥ 1.96 AND sign matches BTC (negative).

Rationale (per memory phase_b2_pattern): new asset scope clears the
single-extreme-BTC stopping rule. Independent-ish edge: same mechanism
(crowded-long funding → price mean-reverts) on a different asset with
different microstructure and options/vol regime.
"""
from pathlib import Path
import numpy as np
import pandas as pd

from atlas.data.derivatives import DerivativesData
from atlas.data.market import MarketData

CACHE = Path("data")
dd = DerivativesData(cache_dir=CACHE / "derivs")
md = MarketData(cache_dir=CACHE)

bmx = dd.fetch_funding_rates("bitmex", "ETH")["fundingRate"]
krk = dd.fetch_funding_rates("krakenfutures", "ETH")["fundingRate"]
bmx.index = pd.to_datetime(bmx.index, utc=True)
krk.index = pd.to_datetime(krk.index, utc=True)
print(f"bitmex ETH: n={len(bmx)} {bmx.index[0]} → {bmx.index[-1]}")
print(f"kraken ETH: n={len(krk)} {krk.index[0]} → {krk.index[-1]}")

start = max(bmx.index.min(), krk.index.min()).ceil("8h")
end = min(bmx.index.max(), krk.index.max()).floor("8h")
grid = pd.date_range(start, end, freq="8h", tz="UTC")

def last_obs(s, idx):
    return s.reindex(s.index.union(idx)).ffill().reindex(idx)

bmx_8h = last_obs(bmx, grid)
krk_8h = last_obs(krk, grid)
df = pd.DataFrame({"bmx": bmx_8h, "krk": krk_8h}).dropna()
df["mean_fund"] = 0.5 * (df["bmx"] + df["krk"])
print(f"aligned 8h rows: {len(df)}")

eth = md.fetch_ohlcv("ETH/USDT", "4h", since="2025-01-01")
eth.index = pd.to_datetime(eth.index, utc=True)
p = eth["close"].sort_index()

def fwd_log(idx, h):
    ei = p.index.searchsorted(idx, side="left")
    out = np.full(len(idx), np.nan)
    for i, e in enumerate(ei):
        if e + h < len(p) and e < len(p):
            p0, p1 = p.iloc[e], p.iloc[e + h]
            if p0 > 0 and p1 > 0:
                out[i] = np.log(p1 / p0)
    return pd.Series(out, index=idx)

df["fwd_8h"] = fwd_log(df.index, 2)
df["fwd_24h"] = fwd_log(df.index, 6)
df = df.dropna(subset=["fwd_8h", "fwd_24h"])
print(f"with ETH fwd returns: {len(df)}")

split_i = int(len(df) * 0.70)
is_df, oos_df = df.iloc[:split_i].copy(), df.iloc[split_i:].copy()
print(f"IS n={len(is_df)} OOS n={len(oos_df)}")

mu, sd = is_df["mean_fund"].mean(), is_df["mean_fund"].std()
is_df["z_mf"] = (is_df["mean_fund"] - mu) / sd
oos_df["z_mf"] = (oos_df["mean_fund"] - mu) / sd

def reg(d, y):
    X = np.column_stack([np.ones(len(d)), d["z_mf"].values])
    yv = d[y].values
    beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
    resid = yv - X @ beta
    n, k = X.shape
    sigma2 = (resid ** 2).sum() / (n - k)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    return beta, se, beta / se, n

for label, d in [("IS", is_df), ("OOS", oos_df)]:
    print(f"\n=== {label} ===")
    for h in ["fwd_8h", "fwd_24h"]:
        b, se, t, n = reg(d, h)
        print(f"{h}: n={n}  const t={t[0]:+.2f}   z_mf β={b[1]:+.5f} se={se[1]:.5f} t={t[1]:+.2f}")
