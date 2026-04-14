<!-- atlas-finding
claim: "Extreme BitMEX BTC funding prints (rolling 1y q01/q99) predict mean-reverting BTC 3-day forward CAR"
experiment_id: funding_reset_events_2026_04_12
spec_hash: B2-funding-reset-q01q99-3d-v1
data_range: "2016-05 to 2026-04"
evidence_class: out_of_sample_test
quality: strong
direction: contradicts
summary: "Crowded-long n=640 OOS p=0.92 mean CAR +0.38%; crowded-short n=122 p=0.79. Null at 3d horizon."
stats:
  n_crowded_long: 640
  p_crowded_long: 0.88
  n_crowded_short: 122
  p_crowded_short: 0.46
generation_method: rolling_quantile_event_study
script: scripts/funding_reset_events.py
-->

# Funding-Reset Event Study on BitMEX BTC — 2026-04-12 (Phase B2, null)

**Null result.** Extreme BitMEX funding prints (rolling 1y q01 / q99) do not predict mean-reverting BTC returns at the 3-day horizon. Finding is recorded so the hypothesis class is marked closed at this specification and Phase B2 can move to liquidation-cascade events instead.

## Pre-registered design

- Data: BitMEX BTC funding rate (10,818 8h prints, 2016-05 → 2026-04) aligned to BTC/USDT 4h returns (22,527 bars).
- Events: funding print above rolling-1y q99 (crowded long) or below rolling-1y q01 (crowded short). Rolling window = 1095 prints (~1 yr) with 365-print warmup. Using rolling rather than global quantiles because global thresholds concentrate events in 2016-2022 (funding regime non-stationary).
- Windows: pre = 6 bars (24h), post = 42 bars (7d). CAR window (0, 18) = 3 days post.
- Controls: 2000 matched non-event windows, buffer ±42 bars, rng_seed=0.
- Rejection: p_two_sided < 0.05 for either tail (crowded-long should have negative CAR; crowded-short positive).
- Temporal split: IS = funding.index[:70%] ≈ pre 2023-04-26, OOS = remainder.

## Results

| Tag | Split | n | mean CAR[0,18] | median CAR | p two-sided |
|---|---|---|---|---|---|
| Crowded long (≥q99) | IS   | 356 | +0.72% | +0.37% | 0.84 |
| Crowded long (≥q99) | OOS  | 284 | +0.38% | +0.05% | 0.92 |
| Crowded long (≥q99) | FULL | 640 | +0.57% | +0.16% | 0.88 |
| Crowded short (≤q01)| IS   |  91 | +4.02% | +2.73% | 0.35 |
| Crowded short (≤q01)| OOS  |  31 | +0.97% | +0.56% | 0.79 |
| Crowded short (≤q01)| FULL | 122 | +3.24% | +1.83% | 0.46 |

## Interpretation

- **Crowded-long signal**: well-powered (n=640). Mean CAR +0.57% is indistinguishable from the control-window mean (p=0.88). **No mean reversion after crowded-long funding prints** at the 3-day horizon.
- **Crowded-short signal**: direction matches the prior (expected positive CAR) with FULL CAR +3.24%, but n=122 and p=0.46 — the result is a directional guess, not evidence. IS mean (+4.02%, n=91) decays to OOS mean (+0.97%, n=31) — consistent with regime-dependent effect, but given the IS p=0.35 the decay is noise on noise.
- Pre-registered significance threshold was NOT met in either tail. Hypothesis is not promoted; the specification is marked closed.

## Why this result is trustworthy as a negative

- n=640 for the primary tail is a lot of statistical power for a 3-day CAR test.
- Matched-control resampling respects non-stationarity — controls are drawn from the same series, so any baseline drift in BTC returns is also in the controls.
- Rolling thresholds avoid the global-quantile early-history concentration.
- IS/OOS split was fixed before inspecting OOS.

## What is NOT ruled out

1. **Intraday (k<6) reversion.** CAR[0,18] integrates 3 days of noise; a fast reversal in the first 4-12 hours could exist and be washed out. Would need a narrower CAR window.
2. **Multi-venue funding dispersion or magnitude-conditioned extremes.** Tested BitMEX alone; a cross-venue extreme (every major venue simultaneously crowded) might carry more signal.
3. **Liquidation-cascade events (Phase B2 proper).** Extreme funding is a stock measure; a liquidation cascade is a flow event. They detect different things.

## Next step

Do not re-test this specification. Phase B2 continues with liquidation-cascade timestamps (different data class, different event timing). If a future hypothesis wants to revisit funding extremes, it must change at least one of: venue scope, horizon, or conditioning variable — otherwise it is a repeat of this specification.

Script: `scripts/funding_reset_events.py`.
