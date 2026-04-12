# Funding-Rate Regime Study — 2026-04-12 (round 5)

BitMEX XBTUSD inverse perp funding, 10,818 rows since 2016-05. First test of a derivatives-native signal.

## Stationarity check: r(funding_t, fwd_return) by year

| Year | r @ 4h fwd | r @ 24h fwd | **r @ 7d fwd** | n |
|---|---|---|---|---|
| 2016 | -0.010 | -0.014 | -0.065 * | 1389 |
| 2017 | -0.031 | -0.013 | +0.001 | 2190 |
| 2018 | -0.026 | **-0.098** *** | **-0.254** *** | 2190 |
| 2019 | -0.052 * | -0.044 * | **-0.199** *** | 2190 |
| 2020 | -0.039 | -0.020 | **-0.163** *** | 2196 |
| 2021 | -0.014 | -0.011 | -0.047 * | 2190 |
| 2022 | +0.013 | +0.031 | -0.037 | 2190 |
| 2023 | -0.063 ** | **-0.136** *** | **-0.182** *** | 2190 |
| 2024 | +0.016 | +0.012 | +0.020 | 2196 |
| 2025 | -0.015 | -0.007 | **-0.153** *** | 2190 |
| 2026 YTD | -0.022 | -0.108 ** | **-0.170** *** | 565 |

## Key finding: cyclical, not decayed

Unlike the lag-6 cross-asset reversal (monotone decay), **funding reversal is regime-switching**:
- Strong bull/trending years (2017, 2021, 2024) → effect weak or reversed
- Range/recovery years (2018-20, 2023, 2025-26) → effect strong (r=-0.15 to -0.25 at 7d)

Interpretation: funding reversal reflects forced deleveraging. In strong trends, the trend dominates any deleveraging effect — overpayers keep getting rewarded by continued direction. In range/recovery regimes, extreme funding reliably precedes mean reversion as overleveraged positions close.

**This is a conditional signal, not a static one.** Any naive trading of funding extremes loses in trending regimes (2017/2021/2024 would bleed) and wins in others. Effect does *not* have the 2020s-decay pattern.

## Signal tests: all failed

18 threshold-based configurations (z ∈ {1.0, 1.5, 2.0} × hold ∈ {6, 42, 84} × fee ∈ {0, 26 bps}). Best zero-fee Sharpe: +0.17, p=0.69. At 26 bps: all negative. Three-day sign-of-funding contrarian: -1.67 Sharpe at 26 bps.

As before: the raw predictive value is real, but *linear* effect with switching sign by regime means a single-threshold signal averages wins and losses to near zero.

## What this means for the next hypothesis

The tradeable form of this signal requires a **regime-conditioner**: predict when the market is in "forced deleveraging regime" vs "trending regime," only apply funding reversal in the former. Candidate regime discriminators:
- Rolling realized volatility percentile (high vol ≈ deleveraging-prone)
- Price distance from 200-day MA (near MA = range-like)
- Funding volatility itself (dispersion across venues would be even better — free via ccxt)

This pivots the search from "find a signal" to "find a regime-classifier that activates the signal." Genuinely higher-EV direction because (a) regime-switching hasn't been arbitraged the same way static lag effects have, and (b) the underlying mechanism (forced liquidation) has structural staying power.

## Infrastructure finding: free funding data is rich

BitMEX (via ccxt, no key) returned **10 years of 8h funding** — this is the deepest free derivatives dataset we've accessed. OKX, Kraken Futures, Bybit (geo-blocked), and Binance Futures (geo-blocked) also expose funding publicly. Cross-venue funding dispersion is a completely unexploited free data axis.
