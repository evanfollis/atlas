# Lead-Lag & Asymmetric Tests — 2026-04-12 (round 2)

Three follow-up threads. **All negative.** All informative.

## Thread 1 — Lead-lag predictability (FALSIFIED broadly)

Tested whether Δ in {Fear&Greed, on-chain volume, hashrate} at t-k predicts BTC daily return at t. Lags: 1, 2, 3, 5, 7, 14 days. **18 tests, 0 significant at p<0.05.**

Largest |corr| was FNG Δ at lag 7: -0.059 (p=0.063). Hashrate correlations all |r|<0.04. On-chain |r|<0.06.

**Knowledge:** The "alt data leads price" thesis at daily horizons is broadly false for these public channels on BTC. *Implication:* Don't build daily-horizon predictive models on FNG/blockchain.info volume/hashrate as direct features. If alt-data has predictive value, it lives at higher frequencies, on derived signals (e.g. exchange-specific flows we don't have), or in non-linear regimes.

## Thread 2 — Asymmetric mean-reversion

Long oversold (z<-1.5σ vs 540-bar baseline) in BEAR (price<200MA): Sharpe 0.16, p=0.78. Bull control had 0 triggers (oversold by 540-bar baseline ∧ above 200MA is empty — the regime definitions are nearly mutually exclusive at this threshold, which is itself a finding: "oversold" already implies bear).

**Knowledge:** Asymmetric long-only mean-reversion in bear regimes ≠ enough alpha to clear costs. Earlier finding (#1 from prior round) about bull regimes punishing shorts stands, but its dual (bear regimes rewarding longs) is not supported. Asymmetry is not a free lunch.

## Thread 3 — Hashrate miner capitulation (FOLK THEOREM FALSIFIED)

The "hashrate dropping >10% from its 30d mean = miner capitulation = local bottom" claim is widely repeated. Tested 3 thresholds × matching hold periods on 8.5yr.

| Threshold | Hold | Sharpe | OOS Return |
|---|---|---|---|
| -5% | 90 bars | -0.12 | -13.8% |
| -10% | 180 bars | -0.24 | -11.4% |
| -15% | 360 bars | -0.41 | -17.9% |

**All three are negative.** Larger drops → worse forward returns (monotone wrong direction). The conventional wisdom is empirically inverted on this sample. *Implication:* Hashrate drawdowns are coincident or lagging, not leading. The "capitulation bottom" narrative may be hindsight pattern-matching to a few cycles (2018, 2022) that don't generalize.

## Summary of compounded knowledge after both rounds

What we now know does NOT work for BTC:
- EOM short (any regime variant)
- SOM long
- Coincidence-trigger signals (2-of-3, 3-of-3 of price/vol/sentiment extremes)
- Daily lead-lag from FNG / on-chain volume / hashrate
- Asymmetric mean-reversion in bear regimes
- "Miner capitulation" hashrate signal (any threshold)

What the system has *proven by elimination*: simple public alt-data + calendar + regime-switching are unlikely to yield clean alpha on BTC at daily/4h horizons after costs. Future cycles should target one of:
1. **Higher frequency** (1h or below) where microstructure dominates — needs orderbook data we don't have
2. **Cross-asset** signals — relative strength rotations (ETH/BTC, SOL/BTC), not single-asset patterns
3. **Derivatives-specific** signals — funding rates, basis, options skew — needs Kraken futures or Deribit
4. **Regime-classification** as a feature, not a gate — predict regime transitions, don't condition on them
