---
name: CAUSAL_LOOP_AUDIT
description: Audit of the Atlas autonomous loop against the principal's causal-mapping intent + realignment plan (handoff atlas-causal-map-loop-realignment-2026-06-09)
type: plan
updated: 2026-06-09T16-30-00Z
---

# Atlas Causal-Loop Audit & Realignment Plan

**Date**: 2026-06-09
**Trigger**: `runtime/.handoff/atlas-causal-map-loop-realignment-2026-06-09.md` — principal
clarified Atlas was **not** intentionally parked/retired. It is meant to keep mapping
crypto-market behavior through falsifiable hypotheses + conjecture/criticism, using a
**causal map** (Pearl-style) to track implications, identify what cannot co-hold, search for
confounders/alternatives, and shape future prediction/pricing-gap work.

This document answers the handoff's 5 questions with primary evidence. It is a **plan**, not a
truth source. ADR/principal-class items are flagged explicitly and are **not** shipped here.

---

## Executive summary

- **The runner is RUNNING** (auto-started on reboot, `active (running) since 2026-06-09 16:03:02 UTC`, PID 790). The "PARKED / STOPPED / retired" disposition in prior `CURRENT_STATE.md` is superseded by the principal's 2026-06-09 clarification.
- **The loop is in a terminal idle state, not a healthy one.** It produces a structurally-empty cycle every hour: 22 signals found → **0 hypotheses generated → 0 evaluated → 0 decisions → 0 graph edges.** Confirmed live in the 16:03Z cycle and in telemetry (`hypotheses_evaluated: 0, decisions_by_kind: {}`).
- **Root cause is a closed loop with no escape hatch** (full chain in Q2). The signal→hypothesis space is a fixed finite enumeration; all enumerable claims have been tested; 69 are FALSIFIED; dedup correctly suppresses re-derivation; the *only* generator that could produce novel hypotheses (`from_graph_gaps`) is gated on a non-empty graph; the graph is populated *only* by promotions; **0 of 76 hypotheses have ever promoted** → the graph file was never created → graph-gap generation is dead-on-arrival. Cold-start deadlock.
- **The principal's causal-mapping vision is architecturally aspirational.** The `CausalGraph` model is a thin networkx DiGraph holding *only promoted primitives*. It has **no representation of confounders, alternative explanations, or mutual exclusion ("what cannot also hold")**, and conjectures never enter it. There is no Pearl-style structure because there are no nodes.
- **The system is good at one thing — killing hypotheses — and bad at the thing the principal wants — building a map.** A falsification is currently a dead end (status=FALSIFIED, thrown away), not a recorded causal claim of *absence*.

---

## Q1 — What already exists, and in what state

| Capability the principal named | Exists? | Where | State |
|---|---|---|---|
| **Hypotheses** (falsifiable, pre-registered) | ✅ Yes | `models/hypothesis.py`; claim/rationale/falsification_criteria/significance_threshold; SHA-256 claim-hash IDs; pre-registration immutable | Working. 76 on disk: **69 falsified, 5 formulated, 2 infeasible, 0 testing**. |
| **Observations** (evidence) | ✅ Yes | `models/evidence.py`; typed by class (backtest/OOS/live)/quality/direction; walk-forward OOS stats | Working. 239 evidence records, all backtest/OOS. **Zero `live_observation` records.** |
| **Conclusions** (decisions) | ⚠️ Partial | `runner.py` decision branches: promote/kill/continue/pivot; `cycle.decision_rationale` one-liner | Only **kill** and **continue** ever fire. 0 promotions ever. No structured closeout. |
| **Lessons** (methodology) | ✅ Yes | `methodology.jsonl`; `compute_method_weights()` Laplace-smoothed per-method promotion rate | Logging works; the *feedback* is inert because promotion rate is 0 for every method. |
| **Causal-graph updates** | ⚠️ Exists, never fires | `models/graph.py` `add_primitive`; called at `runner.py:1155` **only on promotion** | **`graph/causal_graph.json` does not exist on disk.** node_count=0, edge_count=0. |
| **Confounder search** | ❌ None | — | No code searches for confounders or alternative explanations anywhere. |
| **Implication tracking** | ⚠️ Stub, dead | `from_graph_gaps()` generates "downstream implications of validated primitive X" hypotheses | Returns `[]` immediately when `graph.node_count == 0` (hypotheses.py:202). Never produces anything. |
| **Mutual exclusion** ("what cannot co-hold") | ❌ None | — | No representation of contradiction/exclusion between claims in the graph model. |

**Bottom line for Q1:** the *falsification engine* is real and well-tested (168 tests, walk-forward OOS, fee model, Bonferroni, immutable pre-registration). The *causal-mapping layer* is scaffolding that has never carried load.

---

## Q2 — Why the latest cycle generated/evaluated 0 hypotheses and 0 edges

The causal chain, each link evidenced:

1. **Signal scan succeeds.** 16:03Z cycle: 10 BTC + 10 ETH + 1 calendar + 1 cross-asset = 22 signals. (SOL skipped: 0 bars < 833 floor.)
2. **`generate_hypotheses` converts the 22 signals to 22 candidate hypotheses** via templated generators (`hypotheses.py:13-183`). Claim text embeds *quantized* signal parameters (integer lag, discrete MA window, ratio rounded to 1 dp).
3. **Because the detectors use fixed parameters on a stable in-sample window, the same ~22 claims recur every cycle** — the generating process is deterministic given stable data. These exact claims were already formulated and tested in prior cycles.
4. **Dedup correctly suppresses them.** `generate_hypotheses` calls `_find_existing_hypothesis(claim)`; if the existing record's status is `FALSIFIED` or `PROMOTED`, it is skipped (`runner.py:668-673`). With 69 FALSIFIED records, all 22 candidates are already-resolved → dropped.
   - **Direct evidence:** `methodology.jsonl` shows `{"phase":"hypothesis_generation","total_generated":22,"unique":0,"selected":0}` for **every cycle from 2026-05-18T10:52Z through 2026-06-09T16:03Z.** 22 in, 0 out, every time.
5. **Graph-gap generation cannot help.** `from_graph_gaps(graph)` returns `[]` when `graph.node_count == 0` (hypotheses.py:202-203). Graph is empty → no gaps → no novel hypotheses.
6. **Top-up cannot help.** `_top_up_from_formulated_pool` promotes FORMULATED→TESTING only when data is available under STRICT-D2. All 5 FORMULATED hypotheses are environmentally/permanently blocked (off-universe symbols, excluded 4h timeframe). → 0 promoted from pool.
7. **Net: 0 hypotheses** → `run_cycle` hits the `if not hypotheses:` branch (`runner.py:1243`) → emits `cycle.completed` with empty decisions → graph untouched (still 0 nodes/edges) → `consecutive_empty_count` increments (now **374**).

**Why 0 edges specifically:** edges are added only inside `add_primitive` (graph.py:14-19), which is only called on promotion (runner.py:1155). 0 promotions → graph file never written → 0 nodes → 0 edges. The graph is a *projection of promotions*, and there have been none.

**Why 0 promotions ever** (the deeper cause): the gate requires ≥2 *distinct* experiments with **STRONG** support (both Sharpe-significant AND bootstrap-significant) and ≥1 OOS, no strong contradictions (`runner.py:1142`). On 1h crypto price features, after 26 bps round-trip-fee drag and walk-forward OOS, nothing clears that bar — every tested claim falsifies. **This may be correct science (true negatives) or a punitively-calibrated gate; see Q3/routing.**

---

## Q3 — Minimum change to produce high-quality evidence rows or explicit "no action because…" records (not semantic theater)

Three tiers. Only the first is shippable without a principal/ADR decision.

### (3a) Immediate, this-session-shippable — explicit "no-action" record
Today the empty branch logs `"No hypotheses generated this cycle"` and emits a `cycle.completed` with `decisions_by_kind: {}`. That is honest emptiness but it is *opaque*: it does not say **why** there was no action. Replace the silent-empty branch with a structured, machine-readable **no-action record** carrying the diagnosed reason, e.g.:

```
cycle.no_action {
  reason: "hypothesis_space_exhausted",
  candidates_generated: 22,
  unique_after_dedup: 0,
  formulated_pool_blocked: 5,
  graph_nodes: 0,            # → graph-gap generation unavailable
  detail: "all signal-derived claims already FALSIFIED; no novel conjecture available"
}
```

This converts "the loop did nothing" into "the loop did nothing **because** its enumerable hypothesis space is exhausted and the graph is empty" — a true epistemic statement and the honest answer to "is this stuck or done?". **In S3-P2 blast radius** (this branch feeds `_update_streak_counter`/`_maybe_escalate_frozen_loop`), so it must go through `adversarial-review.sh` (or advisor-fallback with the gap disclosed in the commit message, per CLAUDE.md). Does **not** change scientific semantics.

### (3b) Near-term, ADR-class — falsifications become causal-map nodes ("null edges")
**A falsified hypothesis is itself a validated causal claim: "feature X does *not* predict return Y at 1h on BTC after fees."** Today that knowledge is discarded (status=FALSIFIED, never enters the graph). If FALSIFIED claims (with ≥ the same evidence bar that justifies the kill) were written into the causal map as **refuted-edge / absence-of-effect nodes**, then simultaneously:
- the graph stops being empty → `from_graph_gaps` comes alive → genuinely novel hypotheses get generated (breaking the cold-start deadlock);
- the map directly records **"what cannot also hold"** — the principal's explicit ask;
- dedup still prevents wasteful re-testing, but the knowledge is now *positive map content*, not a void.

This is **ADR-class** because it redefines what a graph node means. CLAUDE.md: *"The causal graph earns its name or loses it. Edges must represent tested causal claims, not correlations."* A refuted edge IS a tested causal claim (of absence), so this is arguably *more* faithful to that rule than the current promotions-only graph — but it must be decided, not slipped in. **Route to ADR / principal.**

### (3c) The durable fix for "exhausted backtest space" — see Q5 (forward-prediction ledger)
Backtests on a fixed history are a finite resource; once enumerated, they are exhausted. Forward time is not. The paper-prediction ledger (Q5) generates fresh OOS/`live_observation` evidence every cycle regardless of backtest exhaustion, and it is the only mechanism that can ever satisfy the gate's "≥1 OOS or live_observation" with genuinely out-of-sample data.

---

## Q4 — Data schema for prediction, reasoning, references, observations, closeout, future-self

The existing models cover ~half of this. Proposed additions (concrete, minimal):

| Principal's field | Today | Gap / proposed |
|---|---|---|
| **prediction** | `Hypothesis.claim` is a *standing* claim, not a dated forecast | **New `Prediction` model**: `{hypothesis_id, asof_ts, horizon, statement, falsifier, status: open/scored, score}`. A time-stamped, checkable forward forecast. Enables Q5. |
| **reasoning** | `Hypothesis.rationale` + `falsification_criteria` | Adequate. Keep. |
| **references** | None on the atlas model (canon adapter adds `sources=` only at emit time) | Add `Hypothesis.references: list[SourceRef]` (literature, prior primitives, on-chain dashboards) so provenance lives on the record, not just in the projection. |
| **observations** | `Evidence` (backtest/OOS), 239 records | Schema is fine; the gap is *content*: 0 `live_observation` records. Q5 fills this. |
| **closeout analysis** | `cycle.decision_rationale` one-liner | **New `Closeout` block on Cycle**: `{verdict, was_kill_clean: bool, confounders_considered: [...], alternative_explanations: [...], residual_uncertainty}`. This is where confounder/alternative search (currently absent) gets *recorded* even if initially human/LLM-authored. |
| **future-self suggestions** | `from_graph_gaps` only (dead) | **New `next_cycle_suggestions: list[str]` on the cycle report**, written every cycle (including no-action cycles: "space exhausted → propose new detector class / alt-data source"). Decouples next-step generation from the empty graph. |

These are additive (new optional fields/models); pre-registered-immutability rules still apply to claim/falsification/alpha. **The `Prediction` model and `references` are the only ones that unlock new behavior; `Closeout` + `next_cycle_suggestions` are mostly about making the loop's reasoning legible.** Schema changes are reviewable but not principal-class on their own; they become principal-class when wired to (3b)/Q5.

---

## Q5 — Paper-trading / public-listing analog for calibration data with no live action

**The missing loop: a forward-prediction ledger.** Atlas today only runs *retrospective* backtests on historical data — it never commits to a forward statement and checks it later. That is why it can "exhaust" its evidence: history is finite.

Analog (the crypto equivalent of paper trading / a public prediction-listing):
- Each cycle, for every conjecture that is *not yet falsified* (and, post-3b, for map edges under revalidation), emit a **dated, falsifiable forward prediction** with an explicit horizon and scoring rule — e.g. *"Over the next 7 days, BTC/USDT 1h lag-1 autocorrelation will remain in [−0.05, +0.05]"* or *"a momentum strategy on signal S will not beat buy-and-hold net of 26 bps."*
- Persist it to a **prediction ledger** (append-only, like `methodology.jsonl`).
- When the horizon closes, **score it against realized data** and write a `live_observation` evidence record (the gate explicitly values this: *"≥1 must be out_of_sample_test or live_observation"*).
- Aggregate scores → a **calibration curve** (Brier score / hit-rate vs stated confidence). This is genuine, fresh, un-exhaustible OOS signal, and it is the honest analog of paper-trading P&L without taking any market position.

This also **side-steps the "is the gate miscalibrated?" question**: whether or not the historical falsifications were true negatives, forward predictions generate *new* evidence on a rolling basis, so the system keeps learning even if every backtest in the current feature space is exhausted. No execution layer, no capital, no credentials required (BTC/ETH 1h Bitstamp data already flows).

---

## Routing — what is decidable here vs. what must go to ADR / principal

**Shippable this session (reversible, in-scope):**
- (3a) Explicit `cycle.no_action` record with diagnosed reason — via the S3-P2 review gate.
- `CURRENT_STATE.md` realignment (strip parked/retired; restore running + realigning disposition; correct the escalation-state claim).

**ADR / principal-class (proposed here, NOT shipped):**
1. **Falsifications-as-graph-nodes (3b)** — redefines node semantics; needs an ADR. Highest-leverage single change: it breaks the cold-start deadlock *and* delivers "what cannot co-hold."
2. **Forward-prediction ledger (Q5)** — new subsystem; design + ADR. The durable answer to evidence exhaustion and the calibration ask.
3. **Feature-space expansion (ADR-0033 "Shape 4")** — new detector class + one alt-data source. Alt-data choice needs principal input: funding-rate/OI = no new creds; on-chain (Glassnode) = API key; cross-asset = already available.
4. **Is 0/76 promotions correct science or a miscalibrated gate?** Open question. The strong-both-tests + 26 bps + walk-forward bar may be too punitive, or the null may be real. The Q5 ledger generates fresh evidence either way; do not assume the falsifications are all true negatives.
5. **ADR-0033 disposition** — its "park the loop" recommendation is superseded by the 2026-06-09 principal clarification; its load-bearing *facts* (exhausted generator, 0 promotions) stand. The general session / principal should reconcile the ADR text; this session does not unilaterally rewrite it.

**Do not pause the runner** absent a concrete safety/cost issue (per handoff). Current cost is one Bitstamp scan/hour producing a structurally-empty cycle — cheap, but scientifically inert until at least (3a) lands and an ADR-class change breaks the deadlock.

---

## Implementation log & forward plan (2026-06-28 — principal: "strip theater → ledger")

**Phase 1 — strip theater. DONE + DEPLOYED (commit ec8f4d0).** `from_graph_gaps()` no longer spawns confounder follow-ups from refuted nodes; `backfill_falsified_claims()` no longer projects `confounder_search`-tagged hypotheses. Pruned 4 dishonest nodes (graph 73→69 refuted, 4→0 edges); 5 FORMULATED confounder hypotheses → INFEASIBLE. Loop now emits honest `no_action`. Codex review filed.

**Phase 2 — forward-prediction ledger. Staged 2a/2b/2c.**

- **2a — register + store. DONE + DEPLOYED.** `models/prediction.py` (bucketed id, frozen spec, conservative null default, horizon validation), `storage/prediction_store.py` (append-only, dedup-on-read), `runner.register_predictions()` hooked into `run_cycle` after the scan, `prediction.registered` telemetry. Verified live: **20 forward predictions/cycle** (2 skipped), idempotent per horizon bucket, windows fully forward. `predictions.jsonl` gitignored.
  - **Replayability allowlist (`REPLAYABLE_METHODS`)** — only register signals whose strategy is fully encoded in tags so 2b can replay from `(symbol, timeframe, tags)` alone. **Excluded** (verified each would reconstruct as proxy/fallback, not the claim): `cross_asset_spread`/`lead_lag` (builder falls back to a single-symbol proxy) and composite/calendar generators (no tag-driven branch → generic-momentum fallback). These are deferred until the `Prediction` spec captures what they need (e.g. the partner series). Empirically on the live scan: 20 faithful / 1 proxy / 1 fallback.
  - **Known limitation to address in or before 2b**: `from_autocorrelation_signal` puts the lag in the *claim text* but not the tags, so `_build_signal_from_hypothesis` defaults to lag=1. Reconstruction is therefore *consistent with how the original backtest tested it* (same builder+tags) but the executed strategy may not match the claim's stated lag. Pre-existing (affects the backtest path equally); fix by emitting a `lag_N` tag so claim and strategy agree.

- **2b — score → `live_observation` evidence. NEXT.** For each `predictions.list_due(now)` (status=open, `resolve_ts ≤ now`): fetch OHLCV covering `[window_start − warmup, resolve_ts]`; reconstruct the position series by replaying the **frozen** `strategy_tags` via `_build_signal_from_hypothesis` (build a lightweight `Hypothesis` from `claim`+`strategy_tags`); `run_backtest` on the **scored window only** `[window_start, resolve_ts]` at `fee_bps=26`; write an `Evidence(evidence_class=live_observation, experiment_id=prediction.id)` linked to `hypothesis_id`; set ONLY the resolution fields and `store.update()` (append). **Load-bearing guardrails (from codex review of the 2a model):**
  - *Frozen-spec is enforced by the scorer, not the schema.* Replay only the snapshotted tags; read only `[window_start, resolve_ts]` for the scored returns (warm-up prefix may be read but must not be scored). Any re-detection/re-fit on the forward window voids the OOS-in-time claim.
  - *Append-only discipline.* The scorer sets only resolution fields (`status`, `realized_*`, `brier_score`, `outcome`, `resolved_at`); it must never rewrite forecast fields. The store is last-write-wins, so a forecast-field mutation would silently corrupt the record.
  - *Conservative quality mapping (the spurious-promotion guard).* A single 7d/168-bar window is mostly noise. Map realized → evidence quality conservatively; prefer a Brier-scored probabilistic directional forecast over a Sharpe-significance test. Expect the honest outcome to be `confirmed_null` + a calibration record, NOT promotions. Two lucky non-overlapping windows must not clear the gate's "≥2 distinct strong + ≥1 live_observation" — if the ledger starts promoting on current 1h features, suspect noise first; promotions need new feature space (funding/OI).

- **2c — `atlas calibration` CLI. AFTER 2b.** Hit-rate / Brier across resolved predictions, per claim-type. Emit a distinct register/resolve telemetry split so "honest idle" is distinguishable from "honest productive-but-no-promotion."

**Funding/OI feature expansion** (principal-chosen alt-data, no new creds) remains the Shape-4 follow-on once the ledger is producing calibration data — it is the feature space where a real forward edge (and thus a first promotion) is plausible.
