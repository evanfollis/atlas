# Fear & Greed Extremes → BTC Forward CAR — 2026-04-12 (null)

**Null result at pre-registered spec + underpowered.** alternative.me FNG ≤ 20 / ≥ 80 do not predict directionally-correct BTC forward CAR at the 10-day horizon in the 2023-07 → 2026-04 window. Spec is closed at this horizon and decluster setting.

## Pre-registered design

- FNG daily index (n=1000, 2023-07-16 → 2026-04-11), BTC/USDT daily returns (Kraken).
- Fear tail: FNG ≤ 20 ("Extreme Fear" per publisher). Greed tail: FNG ≥ 80.
- Publisher bounds used rather than data-dredged quantiles.
- Events de-clustered with 10-day minimum spacing (consecutive extreme-fear days don't add independence).
- pre=5, post=20, CAR window (0,10). 2000 matched controls, buffer ±25 days, rng_seed=0.
- Expected sign: fear → positive CAR (contrarian "buy fear"); greed → negative CAR.

## Results

| Tail | Split | n | mean CAR[0,10] | median CAR | p two-sided | Expected sign? |
|---|---|---|---|---|---|---|
| Fear (≤20)  | IS   |  4 | — | — | — | underpowered |
| Fear (≤20)  | OOS  | 12 | −3.01% | −1.02% | 0.63 | **wrong sign** |
| Fear (≤20)  | FULL | 16 | −0.82% | −0.48% | 0.88 | wrong sign |
| Greed (≥80) | IS   |  9 | −0.26% | −2.61% | 0.97 | correct sign but p=0.97 |
| Greed (≥80) | OOS  |  0 | — | — | — | — |

After 10-day de-clustering the sample is small (17 fear / 9 greed events). Every tested cell has p > 0.5. The fear tail has the **wrong sign** — buying into FNG≤20 would have lost 0.82% mean CAR over the next 10 days in this window, not gained.

## Interpretation

- Pre-registered threshold not met in any tail. Hypothesis not promoted; spec closed.
- Fear-tail wrong-sign is interesting but n=16 is too small to make anything of it. The 2023-2026 period featured several "extreme fear" prints followed by further downside (summer 2024, April 2025) before BTC bounced. These nonlinear trajectories are what the 10-day linear CAR fails to capture.
- Greed tail OOS has n=0 — no FNG≥80 prints from 2025-06 onward. This is itself interesting regime content (FNG has never confirmed "extreme greed" in the current rally), but not testable with daily resolution.

## What is NOT ruled out

1. **Longer horizon** (e.g., 60-90d): FNG is plausibly a slow-mean-reversion indicator, not a short-horizon predictor.
2. **Asymmetric threshold** (fear more extreme, e.g., ≤10): the publisher's 20 cutoff produces the same scale of events in very different regimes.
3. **FNG *transitions* rather than levels**: first FNG≤20 print after ≥N days of neutral may differ from a grinding multi-day FNG=15 plateau.
4. **Combined with a positioning variable**: FNG≤20 AND funding-neutralizing OR FNG≤20 AND above-200DMA.

## Pattern across Phase B2 nulls

This is the second Phase B2 null in a row (funding extremes and FNG extremes). Common theme: **single-variable extreme indicators at daily+ horizon on BTC are noise-dominated in 2023-2026**. This matches the lag-6 finding — simple, publicly-visible signals on liquid majors have been competed away. Phase B2 will continue on event-flow data (liquidation cascades) rather than additional stock-positioning extremes.

Script: `scripts/fng_event_study.py`.
