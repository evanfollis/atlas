# Negative Results — 2026-04-12

Four-direction multi-source push. **Zero promotable primitives.** Recording so we don't re-test these.

## What was tested (all on Bitstamp BTC/USD, 4h, walk-forward, 26 bps fees)

| Hypothesis | Window | OOS Sharpe | p | Verdict |
|---|---|---|---|---|
| EOM short (last 3 days) | 11 yr | 0.59 | ~0.30 | Killed — 2yr Sharpe of 1.57 was small-sample artifact |
| SOM long (turn-of-month, equity analog) | 11 yr | -0.04 BTC, -0.80 ETH, -0.16 SOL | n.s. | Killed — equity TOM effect does NOT transfer to crypto |
| EOM short × low-vol regime | 11 yr | 0.71 | 0.24 | Best regime-conditioned variant; still not significant |
| EOM short × bull/bear (200-MA) | 11 yr | 0.48 / 0.17 | n.s. | No edge from trend regime |
| SOL EOM × bull trend | 3.5 yr | 2.16 | — | Almost certainly small-sample again; same trap as #1 |
| 2-of-3 capitulation coincidence (price<-1.5σ ∧ vol>+1.5σ ∧ FNG<25, long, hold 30 bars) | 8.5 yr | 0.11 | 0.84 | Killed — fold Sharpes wildly inconsistent |
| 2-of-3 euphoria coincidence (short) | 8.5 yr | -1.08 | 0.12 | **Directionally wrong** — bull regimes punish euphoria-shorts |
| 3-of-3 coincidence long | 8.5 yr | -0.08 | 0.89 | Killed — 1.5% time-in-market, too rare to matter |

## Knowledge gained (positive epistemic content)

1. **Crypto bull regimes punish symmetric mean-reversion.** Long-on-fear barely works; short-on-greed loses badly. Asymmetry is real and consistent across the 8.5yr FNG sample. *Implication:* future mean-reversion hypotheses should be long-only or regime-gated to bear markets only.

2. **Calendar effects from equities don't transfer.** TOM is the most-replicated equity anomaly; it's absent in crypto. *Implication:* don't port equity calendar literature wholesale; crypto's institutional flow calendar is different (or absent).

3. **2-year backtests systematically overstate Sharpe by ~1σ.** EOM, multi-source, regime — all looked promising at 2yr, all collapsed at 8-11yr. *Implication:* 2yr should not be allowed as the only validation window. Set minimum 5yr where data permits.

4. **Coincidence-trigger signals are too noisy.** Even the most selective 3-of-3 had 1.5% time in market and Sharpe near zero. The signal is correct on average but variance kills it. *Implication:* don't bet on rare-event triggers without mechanism that makes them persist.

## What's left untested (loose threads worth pulling)

- **Lead-lag causal chains.** All tests above used coincidence (X and Y at time t). The actually-unexplored direction: does X at t-k *predict* Y at t? E.g., on-chain exchange inflows lead price by 1-3 days?
- **Asymmetric regime gating.** Mean-reversion long-only in bear markets only.
- **Funding rate as direct flow signal** (not yet tested at all — Bitstamp doesn't have it; needs Kraken or derivs venue).
- **Hashrate/difficulty as miner-capitulation signal** with a real holding period instead of coincidence.
