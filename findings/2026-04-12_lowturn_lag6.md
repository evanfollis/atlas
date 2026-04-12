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

The gross Sharpe is already negative OOS. **This is the decisive fact**: lowering turnover does not help because even zero-fee execution of this expression loses money in 2024+. The β is too small and too noisy to generate tradeable sign predictions at any cadence.

## Why this closes the branch

β shrunk from -0.154 (2018) to -0.026 (2025). At τ=20bp, the predicted magnitude `α + β × btc_lag` rarely exceeds 20 bps in the OOS window (only 50 triggers in 14 months). The few triggers have close to 50/50 directional accuracy — insufficient for a positive gross expectation, let alone one that survives fees.

**The signal is not in a cost basin we can escape by trading less often** — it is below the noise floor for directional prediction in the decay era, period.

## What this jointly says

Combined with the trainable control and the original decay finding, the full conclusion on lag-6 reversal is:

1. The β exists as a statistically real, slowly-shrinking quantity (2018 r=-0.11 → 2025 r=-0.02 annual).
2. A trainable-state implementation correctly tracks the shrinkage but still generates 3-5 flips/day because the sign flips bar-to-bar on near-zero β.
3. Gating on magnitude and increasing hold duration does not rescue the strategy — the signal has deteriorated below directional tradability in 2024+, not just below fee amortization.

**Lag-6 cross-asset reversal is closed as a strategy direction at current retail execution parameters.** Retained as a measurement result (β is real, measurable, and decayed) and as a training example for future methodology. Do not reopen without: (a) sub-4h bars with maker-only execution, or (b) new asset classes (newer majors, SOL or below) where β may still be non-decayed.

## Methodological gain — stop testing harder versions of dead signals

Three successive tests on the lag-6 β (stateless, trainable, low-turnover) all negative. Promote to methodology: **when the simplest honest test of a hypothesis fails cleanly, do not spend more cycles on dressed-up variants unless a specific new mechanism is in scope.** Atlas nearly spent a fourth round on this; the discipline check is to ask "what mechanism would make this work that we haven't already tested?" before committing another cycle. For lag-6 the answer is "maker-only micro-bar execution OR a different asset pair" — both are infrastructure-heavy and not in scope.
