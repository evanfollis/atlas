<!-- atlas-finding
claim: "BitMEX+KrakenFutures mean-funding z-score predicts BTC 24h forward log-return with mean-reversion sign"
experiment_id: dispersion_narrow_2026_04_12
spec_hash: C2-disp-narrow-v1
data_range: "2025-04-09 to 2026-04-12"
evidence_class: out_of_sample_test
quality: moderate
direction: supports
summary: "OOS β(z_mf)=-0.00389 t=-2.41 at fwd_24h, n=331. Interaction z_mf*z_disp null (OOS t=+1.50)."
stats:
  n_oos: 331
  t_stat_zmf_oos: -2.41
  beta_zmf_oos: -0.00389
  t_stat_interaction_oos: 1.50
generation_method: residualized_interaction_narrow_retest
revalidate_after_days: 90
script: scripts/dispersion_narrow.py
-->

# Dispersion Narrow Retest (Phase C2) — 2026-04-12 (null on interaction; baseline replicates)

Narrow retest of cross-venue funding dispersion as an interaction predictor, per codex review #6 design and the Phase B2 memory rule requiring multi-variable conditioning.

## Pre-registered design

- Venues frozen to {BitMEX, KrakenFutures}. OKX excluded (short history distorts statistical meaning across time).
- 8h settlement grid aligned to 00/08/16 UTC. Kraken hourly funding resampled by last-observation-at-or-before (no lookahead).
- `disp = |fund_bitmex − fund_kraken|`. Residualized against `mean_fund` on IS only; IS residual z-scored and applied to OOS.
- Horizons: fwd_8h (2 × 4h bars), fwd_24h (6 × 4h bars), BTC/USDT Kraken.
- Model: `fwd = α + β1·z_mf + β2·z_disp + β3·(z_mf·z_disp)`.
- IS/OOS: first 70% of 8h timestamps IS (n=771), last 30% OOS (n=331). Split = 2025-12-22.
- Reject null iff OOS `|t|` on interaction ≥ 1.96 AND sign matches IS.

## Results

### IS (n=771)

| Horizon | β(z_mf) | t | β(z_disp) | t | β(interact) | t |
|---|---|---|---|---|---|---|
| fwd_8h  | −0.00083 | −1.59 | +0.00010 | +0.25 | +0.00018 | +1.15 |
| fwd_24h | −0.00189 | −2.15 | +0.00060 | +0.85 | +0.00034 | +1.33 |

### OOS (n=331)

| Horizon | β(z_mf) | t | β(z_disp) | t | β(interact) | t |
|---|---|---|---|---|---|---|
| fwd_8h  | −0.00154 | −1.62 | −0.00089 | −0.74 | +0.00022 | +0.68 |
| fwd_24h | −0.00389 | −2.41 | +0.00116 | +0.56 | +0.00083 | +1.50 |

## Interpretation

- **Interaction null.** OOS |t| at 24h is 1.50, short of the 1.96 threshold. The sign is consistent (IS +1.33 / OOS +1.50), which is mildly encouraging — but the pre-registered bar was sign-match AND significance, and that was not met.
- **Mean-funding reversal replicates OOS at 24h** (t=−2.41). This is the cleaner finding: the dispersion-orthogonalized `z_mf` carries a real reversal effect both IS and OOS at the 24h horizon. Consistent with prior work but in a sub-daily window.
- Positive interaction sign (if real) would mean high venue disagreement *attenuates* the mean-funding reversal — venues disagreeing makes the mean a noisier aggregate. That is a sensible mechanism, not evidence for dispersion as independent signal.

## Why this is not a B2-template repeat

Meets all three memory-rule outs: multi-variable conditioning (interaction), sub-daily horizon (8h/24h not daily+), and residualized to isolate orthogonal information. Result is still null, but the test was legitimate rather than a re-dressing of prior specs.

## What is NOT ruled out

1. **Longer multi-venue window.** n=1102 at 8h covers one year; the interaction term has wide error bars. Revisit when KrakenFutures history extends beyond 2 years or a paid source backfills.
2. **Nonlinear conditioning.** Interaction term is linear in `z_mf · z_disp`; bucketing by `z_disp` tertile and fitting `z_mf` slope per bucket might expose a threshold effect the linear product misses. Not pre-registered — flagged for future hypothesis, not tested here.
3. **Alternate dispersion definitions.** Signed `fund_bitmex − fund_kraken` rather than absolute; could distinguish "who is leading" from "how much they disagree."

## Decision

Spec closed. `z_mf · z_disp` interaction does not meet OOS threshold at either horizon. Baseline `z_mf` reversal replicates cleanly OOS at 24h and is worth carrying forward into portfolio-framework work (Phase D1).

Script: `scripts/dispersion_narrow.py`.
