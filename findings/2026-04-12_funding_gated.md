# Regime-Gated Funding Reversal — Negative — 2026-04-12

Tested whether DVOL or realized-vol regime gates separate the "on" and "off" periods of the funding→forward-return reversal. Sample: 1,759 days (2021-06 to 2026-04), BitMEX daily-mean BTC funding vs forward 7d return, BTC DVOL and 30d realized vol as gates (past-only rolling 365d/180d percentiles).

## Ungated baseline

Pooled: r = -0.025, p = 0.29, n = 1759. Weak on this window alone (stronger on longer 10yr BitMEX window, but 10yr window lacks DVOL).

## Gated correlations — opposite of hypothesis

| Gate bucket | r(fund → fwd7) | p | n |
|---|---|---|---|
| DVOL pct 0-33% (low / complacency) | **-0.136** | 0.0001 | 879 |
| DVOL pct 33-67% | +0.082 | 0.06 | 522 |
| DVOL pct 67-100% (high / fear) | +0.053 | 0.31 | 358 |
| RV low | -0.051 | 0.18 | 709 |
| RV mid | -0.075 | 0.10 | 479 |
| RV high | +0.054 | 0.20 | 571 |

The reversal lives in **low-vol** regimes, not high-vol. The original hypothesis (high fear = funding extremes get reversed hardest) is wrong here. Interpretation: in low-vol regimes positive funding is unusual (leverage building into complacency) and more likely to reverse; in high-vol regimes funding tracks realized directional moves rather than leading them.

## Stationarity: the "on" regime doesn't hold

Split the sample in half (2021-06→2023-11 vs 2023-11→2026-04):

| Bucket | H1 r | H1 p | H2 r | H2 p |
|---|---|---|---|---|
| DVOL low (best ungated bucket) | **-0.155** | 0.0001 (n=607) | -0.081 | 0.18 (n=272) |
| RV low | -0.112 | 0.025 | +0.026 | 0.66 |

Even the strongest regime-gated version decays between halves. Consistent with `2026-04-12_lag6_decay.md`: pattern strength attenuates over time, regardless of gate.

## Walk-forward strategy test

Long BTC when funding < threshold AND DVOL pct ≥ gate_thr, 5 OOS folds, 26 bps Kraken fees. **All 9 parameter combinations produce negative Sharpe.** Best: -0.11 (p=0.79). Signal barely fires (0.4–3.1% of bars) because the tested gate is the wrong direction (see above); flipping to DVOL-low gate runs directly into the non-stationarity above and would still post-select.

## Classification

Negative result for the gated-strategy hypothesis. Provides one methodological asset: **the reversal effect concentrates in low-vol regimes, not high**. That contradicts the folk intuition in the original H1 framing and is worth recording.

## What this jointly says with lag-6 decay and dispersion null

Three pattern classes (cross-asset lag reversal, cross-venue dispersion, funding reversal) all show the same structure: strong pooled or historical effects that either decay, localize into episodes, or vanish when fees and stationarity are enforced. The next tracks should move away from micro-structure reversal patterns and toward event/regime-conditional effects (codex #2) and new data sources (on-chain flows, news/events, Substack-sourced hypotheses).
