# Dispersion-as-Gate on Mean Funding Reversal — Partial Positive — 2026-04-12

Follow-up to the dispersion-null result. Hypothesis: cross-venue funding dispersion does not predict returns by itself, but it may *gate* when the mean-funding → reversal effect is strongest (the "confused-market-amplifies-reversal" story).

Sample: 362 multi-venue days (2025-04-09 → 2026-04-05).

## Pooled vs. gated correlations

| Regime | r(mean_fund → fwd7d) | p | n |
|---|---|---|---|
| Ungated | -0.196 | 0.0002 | 362 |
| Dispersion ≥ median | -0.194 | 0.009 | 181 |
| Dispersion < median | -0.143 | 0.055 | 181 |

Pooled split barely moves the effect. Tertile split is similarly flat (t1: -0.10, t2: -0.20, t3: -0.18). On the full window the gate is not doing useful work.

## Half-sample: gate works in H1, collapses in H2

| Half | Dispersion ≥ median | Dispersion < median |
|---|---|---|
| H1 (2025-04 → 2025-10) | **r=-0.42, p<0.0001, n=102** | r=-0.07, p=0.57, n=79 |
| H2 (2025-10 → 2026-04) | r=-0.24, p=0.04, n=79 | r=-0.28, p=0.004, n=102 |

In H1 the gate cleanly separates a strong effect (high disp) from a non-effect (low disp). In H2 both buckets work similarly. That is **not** "stationary gated effect"; it is the same pattern Atlas keeps finding — the pooled/H1 correlations are regime-localized, and the gate that worked in H1 is not the mechanism that drives H2.

## Walk-forward strategy test

Long when mean_fund < 0 AND dispersion ≥ threshold, 3 folds (short sample), 26 bps fees:

| threshold | WF Sharpe | OOS ret% | p | bars active |
|---|---|---|---|---|
| disp ≥ 50th pct | -0.72 | -6.3% | 0.65 | 8.6% |
| disp ≥ 67th pct | -0.58 | -5.2% | 0.71 | 7.5% |

Negative Sharpes. Sample is too short (362 days → ~180 day OOS segments) to resolve a small effect against 26 bps fees.

## Classification

Partial positive on correlation structure (H1 shows dispersion as a meaningful gate), negative on strategy. Not a findable primitive on this window — the stability across halves isn't there, and the strategy bleeds fees.

## What would change the verdict

Needs a much longer multi-venue window. KrakenFutures and OKX are the limiters here (both < 1yr via public API). Backfilling these from a paid source would let us retest with 3-5yr of overlap.

Until then: dispersion-as-gate is a hypothesis to revisit when multi-venue history gets longer, not an actionable signal.
