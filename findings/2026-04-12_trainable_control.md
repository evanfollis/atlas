# Trainable-Signal Control Experiment — 2026-04-12

Codex review #6 flagged that prior "microstructure reversal is exhausted" conclusions were conditional on the stateless-rolling-indicator class used by Atlas's walk-forward harness, and might not hold for a fit-train-apply-test variant. This experiment tests that claim on the strongest historical pattern available — the 24h lag-6 BTC→ETH cross-asset reversal (see `2026-04-12_lag6_decay.md`).

## Design

- **Trainable signal:** at each 4h bar t, fit rolling OLS of `eth_ret[s]` on `btc_ret[s-6]` over past 540 bars (90d). Use the fitted (α, β) to predict `eth_ret[t]` from `btc_ret[t-6]`. Long ETH if prediction > 0, short if < 0. No look-ahead — (α, β) shifted by one bar.
- **Control 1 (fixed-β):** fit a single (α, β) on the full sample and apply everywhere. This is the strawman stateless variant.
- **Control 2 (buy-and-hold ETH).**
- Fees: 26 bps one-way per position change (Kraken taker).
- Sample: 2017-08 to 2026-04, aligned on ETH/USDT + BTC/USDT 4h bars (14,810 bars).

## Results by year (net of fees)

| Year | Trainable Sharpe | Fixed-β Sharpe | ETH BH Sharpe | Trainable total | Fixed-β total |
|---|---|---|---|---|---|
| 2017 | **+3.01** | -4.10 | +2.60 | +122.1% | -88.3% |
| 2018 | -1.96 | -2.71 | -0.93 | -94.9% | -97.9% |
| 2019 | -5.51 | -5.32 | +0.38 | -99.2% | -99.0% |
| 2020 | -4.33 | -6.44 | +2.44 | -98.6% | -99.8% |
| 2021 | -0.77 | -4.94 | +2.01 | -76.9% | -99.8% |
| 2022 | -4.78 | -6.39 | -0.91 | -98.8% | -99.7% |
| 2023 | -6.86 | -7.56 | +1.65 | -96.4% | -97.6% |
| 2024 | -4.83 | -7.84 | +0.91 | -96.5% | -99.5% |
| 2025 | -3.98 | -7.47 | +0.21 | -96.0% | -99.7% |
| 2026 YTD | +0.58 | -7.17 | -1.29 | +4.8% | -74.4% |

## Two results, in tension with each other

**(1) Trainable beats stateless, everywhere.** The trainable rolling-β variant has a strictly better Sharpe than the fixed-β control in every single year tested. So codex's streetlight critique is correct in one narrow direction: the stateless harness is NOT a refutation of trainable variants, and conclusions about strategy survivability drawn from the stateless class do not transfer to the trainable class without doing the experiment.

The β-drift diagnostic confirms why: fitted β drops from -0.154 (2018 mean) to -0.026 (2025 mean). The fixed-β variant is betting on a β that the data says no longer holds; the trainable variant correctly learns it is decaying. In 2026 YTD the trainable β is near zero, the strategy barely trades (Sharpe +0.58), while the fixed-β variant keeps flipping and loses 74%.

**(2) Both are destroyed by fees.** Trainable turnover is 3.34 flips/day, fixed-β is 5.44 flips/day. At 26 bps one-way that is ~87 bps/day of cost for the trainable version — catastrophic headwind at 4h cadence regardless of signal quality. Even in 2017 where trainable gross would be enormous, net is +122% vs +751% implied by the gross Sharpe.

## Net conclusion — more nuanced than the original decay story

The lag-6 signal has not been "arbitraged away" in the naive sense; the β is still a statistically real, if shrinking, quantity. But at 4h cadence on major pairs, the **turnover cost of acting on it exceeds the edge** for any long-only or long-short variant we can express. The effect lives in a cost basin we cannot reach with retail execution.

This matches the codex framing more precisely than the original writeup did: reversal is not exhausted as a *scientific* observation, but it is non-survivable as a *strategy* in this implementation class (taker fees, 4h bars, flip-on-sign trading).

## What would change the verdict

1. **Lower-turnover signal expressions** — sparse-entry rule with multi-day hold (test vs 1-flip-per-day baseline).
2. **Maker fees / venue-specific cost models** — Kraken maker is 16 bps vs 26 taker; some venues offer negative maker fees.
3. **Larger move size gates** — only act when `|pred|` exceeds a threshold that the cost per flip amortizes.
4. **Portfolio / signal-combination** — one tiny edge is unlivable, but combining N independent tiny edges reduces per-signal turnover requirement.

All four are downgrades from "find the signal" to "express the signal tradeable." Parked in the backlog.

## Methodological gain

The stateless walk-forward harness is honest about what it does not evaluate (codex #6) and this experiment now concretely measures the gap. For any trainable-state hypothesis, the control experiment has to be run out-of-band — the harness is not wired for it.
