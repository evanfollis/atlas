# Low-Turnover Lag-6 Expression — Negative — 2026-04-12

Follow-up to `2026-04-12_trainable_control.md`. Tested whether magnitude-gated entry + fixed-hold expression of the trainable rolling-β signal escapes the turnover-cost basin that killed the flip-every-bar version.

## Design

- Rolling-β signal identical to trainable control (90d window, β shifted one bar).
- Gate: enter long/short only when `|pred| > τ`. Hold for H bars. No overlap.
- Sweep: τ ∈ {20, 50, 100, 200, 400} bps, H ∈ {6, 24, 42, 120} bars (1d, 4d, 7d, 20d).
- IS window: pre-2024. OOS: 2024-01-01+.
- Pick best (τ, H) on IS, apply unchanged to OOS. Bonferroni adjust α for the 5×4 = 20 grid.

## Results

**IS sweep (pre-2024, net Sharpe shown):** best cell is τ=20bp, H=42 → Sharpe +0.25 (184 trades). All other cells are negative or trivially sampled.

**OOS with IS-selected (τ=20bp, H=42):**
- Strategy net: total -71.7%, Sharpe -0.85, 50 trades, p=0.270 (not significant, nowhere near Bonferroni α=0.0025)
- Strategy **gross** (zero fees): total -63.3%, Sharpe **-0.63**
- ETH buy-and-hold over same window: -2.9%, Sharpe +0.32

The gross Sharpe is already negative OOS for the IS-selected cell. This rules out fee-amortization as the sole failure mode *for that specific expression*.

**Narrower-than-originally-stated conclusion (codex review #7):** a separate cell (τ=20bp, H=120) has OOS gross Sharpe +0.65 / net +0.56 on about 25 trades, but is IS-negative and p ≈ 0.43 — so it is not cherry-pickable as a rescue. What is proved: **no robust IS-selectable low-turnover expression was found**. What is *not* proved: that no low-turnover expression of this signal can ever work — the H=120 pocket shows cadence still matters even if this particular grid does not produce a defensible strategy.

## Why this closes the branch

β shrunk from -0.154 (2018) to -0.026 (2025). At τ=20bp, the predicted magnitude `α + β × btc_lag` rarely exceeds 20 bps in the OOS window (only 50 triggers in 14 months). The few triggers have close to 50/50 directional accuracy — insufficient for a positive gross expectation, let alone one that survives fees.

**Scope of the closure:** under current retail-style execution (26 bps taker, 4h bars, BTC→ETH only, stateless + trainable + low-turnover grid tested), no robust deployable lag-6 strategy was found. The mechanism itself is not proven dead — alternate pairs, maker-only venues, sub-4h cadence, or a different regime-gating mechanism are each untested.

## What this jointly says

Combined with the trainable control and the original decay finding, the full conclusion on lag-6 reversal is:

1. The β exists as a statistically real, slowly-shrinking quantity (2018 r=-0.11 → 2025 r=-0.02 annual).
2. A trainable-state implementation correctly tracks the shrinkage but still generates 3-5 flips/day because the sign flips bar-to-bar on near-zero β.
3. Gating on magnitude and increasing hold duration does not rescue the strategy — the signal has deteriorated below directional tradability in 2024+, not just below fee amortization.

**Lag-6 cross-asset reversal is closed as a strategy direction at current retail execution parameters.** Retained as a measurement result (β is real, measurable, and decayed) and as a training example for future methodology. Do not reopen without: (a) sub-4h bars with maker-only execution, or (b) new asset classes (newer majors, SOL or below) where β may still be non-decayed.

## Methodological gain — explicit stopping rule

Three successive tests on the lag-6 β (stateless, trainable, low-turnover) all negative. Promote to methodology (refined after codex review #7):

**Stop cycling on a hypothesis when all three hold:**
1. Tested materially different *expression classes* (not just parameter variants of one class).
2. Directly attacked the *dominant failure mode* identified by the prior cycle (here: turnover cost, which the low-turn cycle directly addressed).
3. Remaining variants mostly add degrees of freedom without introducing a new *mechanism*, *market*, or *execution regime*.

For lag-6 under current scope: stateless vs trainable covers the state-handling class; flip-every-bar vs magnitude-gated-hold covers the expression class; β-tracking vs no-tracking covers the dominant failure mode. Remaining untested variants (asymmetric thresholds, regime conditioning, alternate asset pairs) either add degrees of freedom (asymmetric thresholds — codex tried; no rescue) or belong to a separate branch (alternate pairs, regime conditioning with ex-ante mechanism). This justifies closure of the BTC→ETH 4h retail branch, not universal closure.
