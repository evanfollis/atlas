"""First pass event study: BTC daily returns around curated events."""
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.data.market import MarketData
from atlas.data.events import events_in_scope
from atlas.analysis.event_study import event_study


md = MarketData(cache_dir=Path("data"))
btc = md.fetch_ohlcv("BTC/USDT", "1d", since="2016-01-01")
rets = btc["close"].pct_change().dropna()
print(f"BTC daily returns: n={len(rets)} {rets.index[0]} → {rets.index[-1]}")

for cat in ["halving", "regulatory", "collapse", "macro", "fork", "merge"]:
    evs = events_in_scope("BTC", category=cat)
    if not evs:
        continue
    event_dates = [e.date for e in evs]
    try:
        res = event_study(rets, event_dates, pre=5, post=20,
                          car_window=(0, 20), n_controls=2000,
                          buffer=30, rng_seed=42)
    except ValueError as e:
        print(f"{cat:12s}: skipped ({e})")
        continue
    fired = len(res.event_car)
    print(f"{cat:12s} n={fired:2d} meanCAR[0,20]={res.mean_event_car:+.4f} "
          f"medianCAR={res.median_event_car:+.4f} p2={res.p_two_sided:.3f}")
