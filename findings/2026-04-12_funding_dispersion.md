# Cross-Venue Funding Dispersion — Null Result — 2026-04-12

Tested whether dispersion of BTC perp funding rates across BitMEX / OKX / KrakenFutures predicts forward return or realized vol. Hypothesis was that divergence signals stress or arbitrage pressure.

## Data constraints

Effective multi-venue window: 2025-04-09 → 2026-04-05 (362 days).
- BitMEX: 10yr history (2016+) but alone for most of it
- KrakenFutures: 1yr history
- OKX: 95 days (2026-01-08+)

Pre-2025 dispersion is undefined (only BitMEX reporting). Sample for tests is 362 days of 2+ venue coverage; only 95 days have all three.

## Results

| Test | r | p | n |
|---|---|---|---|
| Dispersion → 1d fwd return | -0.02 | 0.75 | 362 |
| Dispersion → 7d fwd return | -0.09 | 0.08 | 362 |
| Dispersion → 7d fwd realized vol | -0.03 | 0.59 | 362 |
| Mean funding → 7d fwd return (baseline) | **-0.20** | **0.0002** | 362 |

Baseline funding reversal replicates. Dispersion itself adds nothing above the mean.

Quintile table shows a weak monotone decline in 7d forward return (Q1 +1.11% → Q5 -0.83%) but stratified p-value is 0.08 and the effect halves in the second half of the sample, so it does not meet the stationarity bar.

## Venue leadership (who diverges predicts what)

On days with all venues reporting:

| Venue | deviation → 7d fwd return | p |
|---|---|---|
| BitMEX | -0.20 | 0.07 |
| OKX | -0.02 | 0.86 |
| KrakenFutures | +0.28 | 0.007 |

BitMEX and KrakenFutures point opposite ways by construction (deviation from mean). With only 95 three-venue days and 6 venue×horizon tests, the KF p=0.007 does not survive multiple-test correction. Marked as a hint, not a finding.

## What killed it

The clean, well-understood effect (mean funding → reversal) is strong on the same window. Any residual signal in the dispersion is small enough that either (a) we need a much longer multi-venue window — which requires waiting or backfilling venue coverage — or (b) the microstructure story (dispersion = arb pressure) just doesn't show up at daily resolution.

## What might still work

- **Intra-day dispersion** at funding-interval cadence (8h), not daily mean. Funding payments settle simultaneously; divergence at settlement is more interpretable than daily averages.
- **Longer multi-venue window** — KrakenFutures data only goes back 1yr via public API. OKX is worse. A paid data provider or scraping deeper history would change the test.
- **Conditional test**: dispersion as a gate on the mean-funding signal, not a standalone predictor. e.g., does "high mean funding AND high dispersion" have larger reversal than "high mean funding alone"? Didn't test — worth a second pass.
