---
name: PASSIVE_INCOME_SLEEVE
description: Atlas as candidate market-modeling sleeve of the passive-income portfolio (ADR-0033)
type: strategy
updated: 2026-05-21
---

# Atlas — Market-Modeling Sleeve Candidate

Per ADR-0033, atlas is being evaluated as sleeve #2 (market-modeling
assets) of the workspace passive-income portfolio, not as another agent-
tooling product. This document enumerates the candidate asset shapes
atlas could take inside that sleeve, the evidence needed for each, and
the recommended next decision.

## Load-bearing empirical fact

Atlas has tested 76 hypotheses across ~28 days of autonomous operation
(2026-04-24 → 2026-05-18). Outcome:

- **0 promoted primitives**
- **69 falsified** (statistical floor failed walk-forward OOS at α=0.05)
- **5 stuck FORMULATED** (all environmentally blocked under STRICT-D2)
- **2 INFEASIBLE** (BitMEX/Kraken Futures — geo-blocked)
- **Signal generator exhausted**: 22 signals/cycle, 0% novel-claim-hash rate

The autonomous loop ran cleanly with three rounds of fixes (A+C+D2, P1
re-eval, S3-P2 counter gate); the methodology held; the gate honestly
fired escalations. None of that was wasted, but the load-bearing
result is that the existing generator-on-Bitstamp-1h-price feature
space does not contain exploitable structure at the gate's pre-
registered significance. That isn't a setback — it's the system
working as designed and reporting null. The strategic options below
all depend on whether and how we change the **feature space being
searched**, because the same search will keep producing the same null.

## Candidate asset shapes

### Shape 1: Strategy-readiness publication (no new primitives required)

What it is: a periodic public artifact (~monthly) listing exactly
which model claims atlas tested, the pre-registered α, walk-forward
methodology, and the outcomes — promoted, falsified, or still in test.
Atlas's `strategy readiness` CLI already produces ~80% of this
content; the remaining work is formatting, hosting, and a stable URL
pattern.

This sits inside sleeve #2 (market modeling) and **not** inside sleeve
#4 (research/content) because the deliverable is *model evidence*, not
editorial opinion or briefs. Buyers are allocators or quant
researchers who care that someone has honestly walk-forward-tested a
hypothesis at a pre-registered alpha; the value is the rigor, not the
prose.

- **Evidence needed**: paid subscribers / paid downloads / paid API
  access; recurring activation independent of principal effort.
- **Dependencies**: none on additional promotions — falsification
  evidence is the *primary* content. ~28 days of methodology +
  76 tested hypotheses is enough corpus for a first issue.
- **Risks**: weak demand. Allocators may prefer named strategies over
  null results. Reputational risk if atlas's methodology is later
  shown to have a gate bug — though the existing adversarial-review
  discipline mitigates this.
- **Automation burden**: medium. ~1 week to wire the CLI output into a
  static publication template + paid-access gate. Hosting via existing
  workspace infrastructure. Re-generation is cron-driven.
- **Time-to-learning**: 2-4 weeks to first issue; 1-3 months to first
  paid signal.

### Shape 2: Signal feed / paper-trading portfolio (conditional on ≥1 promotion)

What it is: when atlas first promotes a hypothesis to a reasoning
primitive, expose its triggers as either (a) a webhook/feed that
fires entry/exit signals, or (b) a public paper-trading book whose
P&L is auditable. Same evidence underlies both; (a) and (b) differ in
fulfillment shape.

- **Evidence needed**: ≥1 promoted primitive surviving the existing
  gate (≥2 strong supports including ≥1 OOS, no strong contradictions).
  Currently 0. Promoted primitive must survive a post-promotion live
  observation window before subscribers see it.
- **Dependencies**: hard-blocked on the generator-exhaustion problem.
  Without expanded feature space (Shape 4), the count will stay at 0.
- **Risks**: regulatory (signal/trading-advice classification varies by
  jurisdiction); reputational on drawdown; selection bias if the
  promotion gate is relaxed under pressure to ship.
- **Automation burden**: high. Signal delivery, subscription billing,
  auth, and audit trail.
- **Time-to-learning**: indefinite — depends on (a) Shape 4 yielding a
  first promotion, then (b) months of live-observation track record.

### Shape 3: Park with explicit unstick triggers

Stop new investment in atlas. Service unit stays stopped (current
state) and codebase remains durable on disk. Restart investment when
one of these *specific* triggers fires:

1. **SOL/USDT 1h on Bitstamp crosses MIN_BARS_FOR_RESEARCH (833 bars)** —
   organic data accumulation. Current bar count is 0; estimated months
   away. Detectable by a cron checking
   `MarketData.fetch_ohlcv("SOL/USDT", "1h")` length.
2. **A new exchange becomes accessible from this host** — would expand
   the symbol/timeframe surface. Current geo-block list: Binance,
   Bybit, BitMEX, Kraken Futures.
3. **A principal-authorized new detector category lands** — e.g.
   on-chain volume, orderbook microstructure, funding-rate divergence,
   cross-asset spread on >2 assets. New detector classes broaden the
   feature space and break generator exhaustion.
4. **Principal P3 decision** (re-add 4h or one-shot kill 4h) resolves
   the 5 stuck FORMULATED entries — unblocks the FORMULATED pool but
   does NOT by itself solve generator exhaustion.

Parking is the honest reflection of "current methodology has searched
and reported null; no path the runner can self-take exists."

- **Evidence needed**: re-evaluate when any trigger fires.
- **Dependencies**: external (data accumulation, exchange access,
  principal decision) or upstream (new detector PR).
- **Risks**: opportunity cost if a market regime change makes existing
  detectors productive again before any trigger fires. Mitigated by
  the fact that the runner is durable and a single `systemctl start`
  resumes from exactly the current state.
- **Automation burden**: zero ongoing. Trigger checks could be cron-
  driven for ~30 minutes of work.
- **Time-to-learning**: triggers may take weeks-to-months. The
  *cost* of waiting is near zero; the *information* gained is
  whether the workspace's other sleeves produce evidence faster.

### Shape 4: Expand the feature space (research investment)

What it is: add detector classes and/or alternative data sources that
operate on feature spaces orthogonal to the current price-1h-Bitstamp
search. Concretely:

- **New detectors on existing data**: regime-conditional (test signal
  only in specific market regimes detected by HMM/threshold),
  cross-timeframe (signals on 1d that trade on 1h), volatility-of-
  volatility, microstructure proxies via OHLCV (high-low-close vs.
  open-close ratios).
- **New alt-data sources** (plumbing exists at `data/alternative.py`):
  on-chain via Glassnode/Coin Metrics community tiers, mining
  difficulty/hashrate, social sentiment (LunarCrush free tier),
  futures-basis aggregates from CryptoCompare.

This is the only path that can break generator exhaustion. Without it,
Shapes 1 and 2 inherit the existing null result; Shape 3 just locks it
in. The investment is engineering time, not capital.

- **Evidence needed**: novel claim-hash rate per cycle > 0; eventually
  ≥1 promoted primitive (gates Shape 2).
- **Dependencies**: developer time. Each detector class is ~1-2 weeks
  including tests and adversarial review. Each new alt-data source
  is ~1 week including caching, schema, and rate-limit handling.
- **Risks**: continued null at higher Bonferroni cost. Survival bias
  from researcher selection of "interesting" detectors. Mitigated by
  pre-registration and the existing adversarial-review discipline.
- **Automation burden**: medium on add (new code + tests); zero
  ongoing (the loop is already automated).
- **Time-to-learning**: 2-4 weeks per added detector/source to know
  whether it produces novel claims at all. Months to first promotion
  if any.

## Selection criteria for atlas's first asset

Mapped against the strategy doc's selection axes:

| Axis                       | Shape 1 (publication) | Shape 2 (signal feed) | Shape 3 (park)  | Shape 4 (expand) |
|---------------------------|----------------------|----------------------|-----------------|------------------|
| Passive potential          | high                 | high                 | n/a (no income) | n/a (input)      |
| Time to first evidence     | 2-4 weeks            | indefinite           | trigger-bound   | 2-4 weeks/detector|
| Capital/legal risk         | low                  | medium-high          | none            | none             |
| Automation burden          | medium               | high                 | zero            | medium           |
| Dependency on third parties| low                  | medium (billing)     | external trigger| medium (alt-data APIs)|
| Evidence quality           | already corpus       | requires promotion   | n/a             | required upstream|
| Compounding to system      | medium               | high                 | low             | high             |

## Recommendation

**Combine Shape 3 (park atlas's *autonomous loop*) with bounded Shape
4 (one new detector category + one new alt-data source as a single
research investment), and revisit in 4-6 weeks.**

Why this combo, not pure park or pure expand:

- Pure park accepts the current null without testing whether expanded
  feature space changes the result. The empirical track record is
  load-bearing evidence about a *specific* search; it does not
  generalize to "atlas's thesis is dead."
- Pure expand burns engineering time on a sleeve whose passive-income
  shape (Shape 1 or 2) is still uncertain. Open-ended detector work
  without a deadline could absorb arbitrary time.
- The combo: one detector class + one alt-data source is a bounded
  experiment (~3-4 weeks of engineering). If after that the system
  produces novel claim hashes and at least one progresses toward
  promotion, atlas justifies further investment toward Shape 2 (paid
  signal feed). If not, the null is now load-bearing against the
  *broader* feature space and atlas moves to Shape 3 (park) or
  Shape 1 (publication) honestly.

Concrete first investment proposal (sized for 3-4 weeks):
- **One new detector class**: regime-conditional signals (run an HMM or
  threshold-based regime detector on the OHLCV history; permit signal
  to fire only in specific regimes). Rationale: existing detectors
  fire across all regimes, diluting their power in mixed conditions.
- **One new alt-data source**: free-tier on-chain (Glassnode community
  endpoints for active addresses, exchange flows). Rationale: lets
  existing detectors search a feature space the workspace doesn't
  currently see.

Shape 1 (publication) becomes available as a fallback if the bounded
expansion produces no novel claims — the existing falsification
corpus is already large enough to make a first issue informative.

Shape 2 (signal feed) is explicitly deferred — it depends on Shape 4
yielding a promotion, which is not the immediate proposal.

## Out of scope for atlas

- Manual sales / outreach (violates passive constraint).
- Editorial briefs or opinion pieces (sleeve #4, not sleeve #2).
- Live capital allocation (gated behind evidence, not on the table now).
- Synaplex/skillfoundry integration (separate sleeves).

## Open questions for principal

1. Is the bounded Shape 4 investment (3-4 weeks engineering, one
   detector + one alt-data source) within atlas's authorized scope,
   or should that be parked too?
2. If the bounded expansion produces no novel claims, is Shape 1
   (publication) authorized as the next experiment, or does atlas go
   to long-term park?
3. P3 (4h re-add vs one-shot kill) — separable from the above; clears
   noise either way. Lower stakes given recommendation above.
