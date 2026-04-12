# Cross-Asset Lag-6 Reversal — 2026-04-12 (round 3)

**First replicated statistical pattern in three rounds.** Real, but untradeable as designed.

## The pattern

At lag = 6 four-hour bars (24 hours), all five tested cross-asset return pairs show **negative** correlation, p < 0.0001:

| Pair | r at lag-6 (24h) | n |
|---|---|---|
| BTC → ETH | -0.076 | 18,963 |
| ETH → BTC | -0.081 | 18,963 |
| BTC → SOL | -0.060 | 7,996 |
| SOL → BTC | -0.048 | 7,996 |
| SOL → ETH | -0.045 | 7,996 |

Additionally: at lag-3 (12h), BTC↔ETH show *positive* correlations of similar magnitude. The microstructure looks like **12h momentum → 24h reversion** in cross-asset spillover.

This is consistent with: (a) overshoot/correction dynamics across the major caps, (b) cross-margined liquidations cascading then reverting, or (c) market-makers absorbing one-sided flow on lag-3 then unwinding by lag-6.

## Why it didn't trade

Tested 25 threshold-signal configurations (5 pairs × 5 hyperparam sets). All were near-zero or negative Sharpe at 26 bps. Fee sensitivity for the cleanest case (trade ETH on BTC's lag-6 z, threshold=1.0, hold=6):

| Fee | Sharpe | OOS Return | p |
|---|---|---|---|
| 0 bps | +0.38 | +20.1% | 0.56 |
| 2 bps | +0.32 | +12.9% | 0.61 |
| 5 bps | +0.24 | +3.0% | 0.71 |
| 10 bps | +0.09 | -11.7% | 0.88 |
| 26 bps | -0.36 | -46.1% | 0.58 |

**Even at zero fees, the threshold signal does not reach significance.** The linear predictive value (r=-0.07) is real, but a discrete entry/exit on z-score throws away most of it — too many trades, too much noise per trade.

## Knowledge gained

1. **Cross-asset spillover IS predictable at 24h horizon for crypto majors.** This is a real microstructural effect, replicated across 5 pairs, p<0.0001. Not luck.
2. **Discrete threshold signals are not the right extraction method.** The signal is in the *magnitude* of the lagged return, not in extreme z-scores. To trade it: continuous-position regression or ML model that sizes position to expected-return.
3. **The fee floor for this signal class is ~5-10 bps round-trip.** At Kraken taker (26 bps each side = 52 bps round-trip), it's dead. Maker rebates (~0-2 bps) make it borderline. Effect needs to be >0.15 expected return per trade to clear fees, which a small-r linear predictor produces only on extreme leader moves.

## Tradeable directions remaining

- **Continuous-position regression** sized by expected return (β × lagged_leader_return), then evaluate at maker-fee assumptions. The conservative way: on each bar, position = clip(α × leader_lagged_z, -1, 1), no thresholds.
- **Combine lag-3 momentum + lag-6 reversion** as opposing signals — the asset that just moved 12h ago in one direction is more likely to reverse in 12 more hours. Conditional signal might have better SNR.
- **Funding rate** as the next data axis to plumb (Kraken futures). Funding extremes have a real behavioral cause (forced position rotation) that doesn't apply to the spot patterns we've exhausted.

## Status of the autonomous research program

After 3 rounds we have:
- 1 replicated statistical pattern (cross-asset lag-6 reversal)
- 0 tradeable signals after costs
- Eliminated: calendar effects, single-asset MR, alt-data lead-lag, hashrate, ratio MR/momentum, threshold cross-asset signals
- Compounded knowledge: each negative result narrows the next cycle's search

The system is doing what it should: refusing to promote noise. The first real signal turned out to be sub-fee. That's a successful finding — it tells us where the real edges live (continuous predictors, lower fees, derivatives data) without burning capital to learn it.
