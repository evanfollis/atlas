# z_mf Cross-Asset Robustness on ETH — 2026-04-13 (weak, not significant)

Tests whether the BitMEX+KrakenFutures mean-funding reversal (replicating OOS on BTC at 24h, t=−2.41) generalizes to ETH.

## Pre-registered design

- Same venue set (BitMEX ETH/USDT:USDT linear, KrakenFutures ETH/USD:USD), 8h grid, same IS/OOS split rule (first 70%).
- Univariate model: `fwd = α + β·z_mf`. No dispersion.
- Horizons: fwd_8h, fwd_24h on ETH/USDT Kraken closes.
- Reject null: OOS |t| ≥ 1.96 AND sign matches BTC (negative).

## Results

| Split | Horizon | n | β(z_mf) | t |
|---|---|---|---|---|
| IS  | 8h  | 772 | +0.00021 | +0.28 |
| IS  | 24h | 772 | −0.00075 | −0.56 |
| OOS | 8h  | 331 | −0.00093 | −1.26 |
| OOS | 24h | 331 | −0.00145 | −1.13 |

## Interpretation

- OOS sign matches BTC (negative, i.e. reversal) at both horizons, but |t| maxes at 1.26 — does not clear the 1.96 bar.
- IS is essentially noise (t=−0.56 at 24h), so this is not even an IS-selected-OOS-decayed pattern; it is weak throughout.
- BitMEX ETH history is shorter (2021-11+ vs 2016+ for BTC) and uses the linear ETH/USDT:USDT perp — the inverse ETH perp was delisted. Funding regime may differ from the BTC inverse perp.

## Decision

z_mf reversal does **not** robustly generalize to ETH at this venue set and window. The edge, to the extent it exists, is BTC-specific. Do not use ETH as a confirming independent edge for portfolio (Phase D1). Treat the BTC-24h z_mf result as a single-asset finding rather than a cross-asset mechanism.

## What is NOT ruled out

- Longer window or different venue set (e.g., OKX ETH funding once its history accumulates).
- Different horizon on ETH (48h+, or sub-8h).
- Conditional on BTC z_mf (ETH lag behind BTC funding).

Script: `scripts/zmf_eth.py`. Mapping fix: `src/atlas/data/derivatives.py` ETH on BitMEX is linear `ETH/USDT:USDT` (inverse delisted).
