# DVOL (Deribit Implied Vol Index) — First Look — 2026-04-12

> **STATUS: DOWNGRADED 2026-04-12 (same day).** The 60-80% bucket pattern below does **not** survive a rigorous followup (`/tmp/dvol_rigorous.py`) and a codex adversarial review. See "Rigorous followup" section at bottom. Treat the table below as an exploratory summary, not a finding. The bucket claim is an episode cluster, not a stable primitive. Do not build on it without the rebuttal test (freeze rule pre-2024, episode-level bootstrap, report 2024-2026 only).


First hypothesis test against fresh options-implied vol data. 1,789 daily observations (2021-04 to 2026-03).

## Stationarity: linear DVOL effects fail the check

| Hypothesis | Pooled r | Pooled p | Stationary by year? |
|---|---|---|---|
| DVOL level → fwd 7d | -0.03 | 0.23 | n/a (not significant) |
| DVOL level → fwd 30d | **-0.11** | <0.0001 | **NO** — 2022 +0.10, 2024 -0.35, flips sign |
| DVOL Δ7d → fwd 7d | +0.07 | 0.005 | **NO** — 2023 +0.17 sig, 2025 -0.08 |
| DVOL Δ7d → fwd 30d | +0.03 | 0.25 | n/a (pooled not significant) |
| (IV − RV) spread → fwd 30d | -0.05 | 0.04 | **NO** — 2024 +0.20, 2025 -0.38 |

All three linear hypotheses (level, change, spread) have pooled significance but fail stationarity. Consistent with lag-6 finding: pooled r is often a weighted mean of regime-dependent effects that cancel in any deployed strategy.

## H4: Non-linear DVOL percentile bucketing — genuinely interesting

Bucketing DVOL by its rolling 1-year percentile:

| DVOL percentile | Mean fwd 7d | Mean fwd 30d | n |
|---|---|---|---|
| 0-20% (complacent) | -0.07% | +1.58% | 702 |
| 20-40% | +0.65% | +2.00% | 339 |
| 40-60% | +1.10% | +2.04% | 271 |
| **60-80% (moderate fear)** | **+1.55%** | **+7.98%** | 248 |
| 80-100% (panic) | +0.86% | +0.55% | 170 |

The 60-80% bucket is ~3x-5x higher forward return than any other bucket, on a meaningful sample (n=248 independent observations).

**Counter-intuitive but coherent interpretation:**
- 0-20% complacency → low forward return (pre-shock regime; vol is mean-reverting up)
- 80-100% panic → low forward return (active crisis; not yet the bottom)
- 60-80% moderate fear → high forward return (post-shock recovery; options still pricing fear premium while price has already stopped falling)

This rhymes with equity-VIX research: extreme VIX spikes coincide with drawdowns in progress, not bottoms; the bottom is typically marked by *elevated-but-stable* VIX.

## Caveats before any strategy build

1. **Short sample:** 5 years (2021-2026). The DVOL index only started 2021. Can't apply the decade-scale stationarity check.
2. **248 observations in the hot bucket** — respectable but not huge; the +8% mean 30d return has wide CI.
3. **Overlapping returns:** 30-day forward returns with daily observations have massive serial dependence; naive p-values overstate significance. Must test with block bootstrap before any claim.
4. **Regime timing:** most of the "moderate fear" bucket observations likely concentrate in specific episodes (Mar 2023 banking, Oct 2023 ETF anticipation, mid-2024 post-ETF dip, 2025 Q1 dislocation?). Need to check episode coverage before treating as a general pattern.
5. **Strategy conversion:** the simplest test is a regime-filter ("long BTC when DVOL pctile ∈ [0.6, 0.8]") with walk-forward validation and fee model. This is the next experiment.

## What's still worth testing

- Bucketed fwd 7d and 30d with **bootstrap-CI and block bootstrap** on the 60-80% bucket specifically
- **Stationarity of the H4 pattern by year** (split 2021-23 vs 2024-26; does the bucket ordering hold?)
- **Episode decomposition**: does the high-return bucket concentrate in 2-3 specific episodes, or is it distributed across the sample?
- **Translated to a strategy**: regime filter "long when DVOL pct in [0.5, 0.85]" with walk-forward, stationarity, fee sensitivity

## Infrastructure delivered this session

- `src/atlas/data/derivatives.py` — DerivativesData class fetching cross-venue funding (BitMEX/OKX/KrakenFutures) and Deribit DVOL. Free, no key, cached CSV.
- `src/atlas/data/dune.py` — DuneClient class; executes saved queries with cache. Auth via DUNE_API_KEY env var (stored in atlas/.env, gitignored, chmod 600). Free tier verified working.
- Smoke tests pass: 5yr of DVOL, 1yr KF funding, 3mo OKX funding, 4957 CEX-labeled addresses via Dune.

## Rigorous followup (same-day) — DOWNGRADES the bucket claim

Script: `/tmp/dvol_rigorous.py`. Codex adversarial review: see session notes.

1. **Episode concentration invalidates the n=248 "independent observations" framing.** The 257 hot-bucket daily rows collapse to **26 episodes** (gap>7d). With a 30d forward-return target, adjacent signal days share almost identical payoff paths. Effective sample size is ~26, not 248.

2. **Stationarity fails.** First half: 42 hot obs, modest mean. Second half: 215 hot obs, drives the entire pooled +7.98% figure. That is a clustered regime-localized effect, not a stable pattern.

3. **Block bootstrap (block_size=30) CI** for pooled hot bucket 30d return: [+3.38%, +14.34%] — looks good, but block bootstrap on daily rows is still not an episode-level test when obs cluster into 26 episodes.

4. **Walk-forward strategy test (26 bps Kraken fees):** Sharpe 0.39, p=0.37 across 5 folds. Not significant. Fold Sharpes: highly uneven, episode-driven.

5. **Post-selection bias:** the intervals tested `[0.6,0.8)`, `[0.5,0.85)`, `[0.4,0.9)` were picked *after* seeing the bucket table. The walk-forward p-values do not price that search.

## Rebuttal test that would revive the claim

Per codex: freeze the rule on pre-2024 data only, use **one non-overlapping entry per episode** or a true episode bootstrap, then report strategy performance on 2024-2026 with no re-tuning. If that survives, the pattern is interesting. If not, it is a well-labeled episode cluster.
