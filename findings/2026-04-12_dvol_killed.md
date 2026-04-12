# DVOL 60-80% Bucket — Killed — 2026-04-12

Rebuttal test designed by codex review #5 applied. The pattern does not survive.

## Test design (frozen before looking at OOS)

1. Rule frozen on IS (pre-2024): DVOL percentile ∈ [0.6, 0.8) on a past-only 365d rolling rank.
2. Episode-level entries: one trade per episode (gap > 30d ends episode). No overlapping entries.
3. OOS window: 2024-01-01 → 2026-03-13.

## Results

**In-sample (pre-2024):** 8 episodes, mean fwd-30d return **+0.78%**. The previously-reported +7.98% was an artifact of overlapping daily entries in the same episodes — episode-adjusted effect is ~10× smaller than the pooled statistic suggested.

**Out-of-sample (2024+):** 6 episodes, mean fwd-30d return **-2.19%**.

| OOS entry | fwd-30d return |
|---|---|
| 2024-01-12 | +12.94% |
| 2024-04-26 | +7.44% |
| 2024-07-17 | -8.13% |
| 2025-03-04 | -4.71% |
| 2025-11-15 | -9.55% |
| 2026-02-01 | -11.12% |

Episode bootstrap 95% CI: [-9.03%, +5.33%]. Zero in CI.

**Strategy PnL (long 30d at each OOS episode entry, 52 bps round-trip):**
- 6 trades, mean net -2.71%, compounded **-17.31%**.
- BTC buy-and-hold over the same window: **+60.57%**.

The strategy loses money both absolutely and dramatically vs. buy-and-hold.

## Classification

Hypothesis **killed**. Episode-level analysis on IS already collapses the effect to a fraction of the pooled number; OOS flips sign with a large negative magnitude. No residual claim to preserve.

## Methodological lesson (promoted, with caveat)

On this dataset, pooled mean (+7.98%) / episode-adjusted mean (+0.78%) ≈ 10×, which matches the days/episodes ratio (257/26 ≈ 10×). That coincidence is **not a universal law** — the ratio only approximates inflation when within-episode forward returns are essentially identical (i.e., a cluster of daily firings is really one trade). More generally, overlap is a dependence problem, not a fixed multiplicative factor (codex review #6).

**Add to methodology:** any hypothesis using overlapping forward returns must use cluster-aware inference — episode bootstrap, one-entry-per-episode sampling, or cluster-robust SEs. Report the episode-adjusted effect as primary, pooled as diagnostic only. The days/episodes ratio is a useful red flag for how severe the overlap is, not a correction factor.
