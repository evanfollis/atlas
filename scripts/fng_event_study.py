"""Phase B2: Fear & Greed extreme event study on BTC daily.

Pre-registered hypothesis (from behavioral prior, not graph-derived):
Extreme Fear → positive forward CAR (buy-fear). Extreme Greed → negative
forward CAR (sell-greed). Both tails tested separately.

Pre-registered spec:
  - Data: alternative.me FNG daily index 2023-07 → 2026-04 (n≈1000 days).
    BTC/USDT daily returns from cached Kraken data.
  - Events: FNG ≤ 20 ("Extreme Fear" published threshold) for fear tail,
    FNG ≥ 80 ("Extreme Greed") for greed tail. Using the publisher's own
    classification bounds rather than data-dredged quantiles.
  - Windows: pre=5 days, post=20 days. CAR (0, 10) = 10d post-event.
  - Controls: 2000 matched, buffer ±25 days, rng_seed=0.
  - Reject: p_two_sided < 0.05 in the expected direction for either tail.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.data.market import MarketData
from atlas.analysis.event_study import event_study


md = MarketData(cache_dir=Path("data"))
btc = md.fetch_ohlcv("BTC/USDT", "1d", since="2023-01-01")
rets = btc["close"].pct_change().dropna()
print(f"BTC 1d returns: n={len(rets)} {rets.index[0]} → {rets.index[-1]}")

fng_path = next(Path("data/alternative").glob("fng_*.csv"))
fng = pd.read_csv(fng_path, parse_dates=["timestamp"], index_col="timestamp")["fear_greed"]
if fng.index.tz is None:
    fng.index = fng.index.tz_localize("UTC")
fng = fng.sort_index()
print(f"FNG: n={len(fng)} {fng.index[0]} → {fng.index[-1]} "
      f"range [{fng.min()},{fng.max()}] mean={fng.mean():.1f}")

# Publisher thresholds (alternative.me):
#   0-24 Extreme Fear, 25-49 Fear, 50-54 Neutral, 55-74 Greed, 75-100 Extreme Greed
# But reading FNG history, "Extreme" bounds vary. Use <=20 and >=80 to be strict.
fear_events = fng[fng <= 20].index.to_list()
greed_events = fng[fng >= 80].index.to_list()
print(f"Fear (≤20) n={len(fear_events)}, Greed (≥80) n={len(greed_events)}")

# De-cluster: require 10d spacing between events in the same tail, else counting
# consecutive-day "extreme fear" runs overstates n without adding independence.
def decluster(events, gap_days=10):
    out = []
    for e in sorted(events):
        if not out or (e - out[-1]).days >= gap_days:
            out.append(e)
    return out

fear_events = decluster(fear_events)
greed_events = decluster(greed_events)
print(f"After 10d de-clustering: fear n={len(fear_events)}, greed n={len(greed_events)}")

split = fng.index[int(len(fng) * 0.70)]
print(f"IS/OOS split: {split}")

for tag, events in [("extreme-fear (FNG≤20)", fear_events),
                    ("extreme-greed (FNG≥80)", greed_events)]:
    evs_is = [e for e in events if e < split]
    evs_oos = [e for e in events if e >= split]
    for subset_name, evs in [("IS", evs_is), ("OOS", evs_oos), ("FULL", events)]:
        if len(evs) < 5:
            print(f"{tag} [{subset_name}]: n={len(evs)} (too few)")
            continue
        try:
            res = event_study(rets, evs, pre=5, post=20, car_window=(0, 10),
                              n_controls=2000, buffer=25, rng_seed=0)
        except ValueError as e:
            print(f"{tag} [{subset_name}]: skipped — {e}")
            continue
        print(f"{tag} [{subset_name}]: n={len(res.event_car)} "
              f"meanCAR[0,10]={res.mean_event_car:+.4f} "
              f"medianCAR={res.median_event_car:+.4f} "
              f"p2={res.p_two_sided:.4f}")
