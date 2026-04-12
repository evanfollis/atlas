"""Phase B2: funding-reset event study on BitMEX BTC.

Hypothesis (pre-registered here, not in a hypothesis JSON yet): extreme
funding-rate prints mark crowded-one-side positioning; subsequent 4h bars
should mean-revert against the crowd.

Events are funding prints above q99 (crowded long, expect negative CAR) or
below q01 (crowded short, expect positive CAR). We run two separate event
studies so the signs stay interpretable instead of cancelling.

Pre-registered:
  - pre = 6 bars (24h), post = 42 bars (7d) of 4h BTC returns
  - CAR window = (0, 18) = 3 days post-event
  - n_controls = 2000, buffer = 42 bars (= full post window)
  - rng_seed = 0
  - Reject null at p_two_sided < 0.05 for either tail
"""
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.data.market import MarketData
from atlas.analysis.event_study import event_study


md = MarketData(cache_dir=Path("data"))
btc = md.fetch_ohlcv("BTC/USDT", "4h", since="2016-01-01")
rets = btc["close"].pct_change().dropna()
print(f"BTC 4h returns: n={len(rets)} {rets.index[0]} → {rets.index[-1]}")

funding = pd.read_csv(
    "data/funding_bitmex_btc.csv", parse_dates=["timestamp"], index_col="timestamp"
)["fundingRate"]
# Normalize tz
if funding.index.tz is None:
    funding.index = funding.index.tz_localize("UTC")
print(f"Funding prints: n={len(funding)} {funding.index[0]} → {funding.index[-1]}")

q01 = float(funding.quantile(0.01))
q99 = float(funding.quantile(0.99))
print(f"Thresholds: q01={q01:+.5f}  q99={q99:+.5f}")

# Global thresholds concentrate events in early history (funding regime
# non-stationary). Use rolling 1-year quantile thresholds so events
# distribute across time. Lookback = 1095 prints ≈ 1yr at 8h cadence.
roll = funding.rolling(1095, min_periods=365)
hi_thr = roll.quantile(0.99)
lo_thr = roll.quantile(0.01)
high_mask = funding >= hi_thr
low_mask = funding <= lo_thr
high = funding[high_mask].index.to_list()
low = funding[low_mask].index.to_list()
print(f"Extreme events (rolling-1y q01/q99): high n={len(high)}, low n={len(low)}")

split = funding.index[int(len(funding) * 0.70)]
print(f"IS/OOS split: {split}")

for tag, events in [("crowded-long (high funding)", high),
                    ("crowded-short (low funding)", low)]:
    evs_is = [e for e in events if e < split]
    evs_oos = [e for e in events if e >= split]
    for subset_name, evs in [("IS", evs_is), ("OOS", evs_oos), ("FULL", events)]:
        if len(evs) < 5:
            print(f"{tag} [{subset_name}]: n={len(evs)} (too few)")
            continue
        try:
            res = event_study(
                rets, evs, pre=6, post=42, car_window=(0, 18),
                n_controls=2000, buffer=42, rng_seed=0,
            )
        except ValueError as e:
            print(f"{tag} [{subset_name}]: skipped — {e}")
            continue
        print(f"{tag} [{subset_name}]: n={len(res.event_car)} "
              f"meanCAR[0,18]={res.mean_event_car:+.4f} "
              f"medianCAR={res.median_event_car:+.4f} "
              f"p2={res.p_two_sided:.4f}")
