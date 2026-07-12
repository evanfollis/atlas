---
name: CURRENT_STATE
description: Front door for atlas — live research-loop state, canon gap closure status, deployment mode
type: front-door
updated: 2026-07-12T04:15:50Z
---

# CURRENT_STATE — atlas

**Last updated**: 2026-07-12T04:15:50Z — Prompteval governance handoff refreshed for atlas at `/opt/workspace/runtime/.handoff/atlas-prompteval-governance-2026-07-12.md` (`task_id=atlas-prompteval-governance-2026-07-12`). It is informational: `/opt/workspace/supervisor/scripts/prompteval scan /opt/workspace/projects/atlas` currently reports `no likely prompt artifacts found`, so ADR-0039 does not block Phase 2c. If atlas later adds an LLM call, agent charter prompt work, or prompt-building code, run `create-eval-loop` and pass `prompteval check .` before shipping. **NEXT remains Phase 2c** (`atlas calibration` CLI) — blocked on fixing `predicted_prob_up`; then P2 pool fix + unreplayable logging. — *Prior context below.*

**Previous (2026-07-12T03:53:41Z)** — Prompteval governance handoff created/updated for atlas at `/opt/workspace/runtime/.handoff/atlas-prompteval-governance-2026-07-12.md` (`task_id=atlas-prompteval-governance-2026-07-12`). It is informational: atlas currently has 0 likely prompt artifacts, so ADR-0039 does not block Phase 2c. If atlas later adds an LLM call, agent charter prompt work, or prompt-building code, run `create-eval-loop` and pass `prompteval check .` before shipping. **NEXT remains Phase 2c** (`atlas calibration` CLI) — blocked on fixing `predicted_prob_up`; then P2 pool fix + unreplayable logging.

**Previous (2026-07-12T03:34:13Z)** — GitHub source repo established/verified as `evanfollis/atlas` and current tracked state is being pushed to `origin/main`. Local delta before push: one reflection commit plus runner-updated `graph/causal_graph.json` confidence/evidence changes. After this push, remote `origin/main` is expected to include the current front-door state and graph drift. **NEXT remains Phase 2c** (`atlas calibration` CLI) — blocked on fixing `predicted_prob_up`; then P2 pool fix + unreplayable logging.

**Previous (2026-07-12T02:19:18Z)** — reflection pass. **Phase 2b is live and delivering.** Bucket 2948's 20 expired predictions scored autonomously (18 confirmed_null / 1 inconclusive / 1 edge_appeared; evidence 253→273). Bucket 2949 (20 open) will score autonomously 2026-07-16; no attended session needed. Lag-tag gap (28th carry-forward) **resolved** — `from_autocorrelation_signal` now emits `lag_N`. Two stale URGENTs deleted. Branch pushed (origin in sync). **Codex review ran** (`ledger-2b-scorer-2026-07-11.md`); 3 findings marked "pre-existing/guarded" without individual dispositions — gap noted. **Brier score degenerate** (`predicted_prob_up` always 0.5) — 2c calibration meaningless until fixed. `skipped_unreplayable: 2` — 29th window, still no ID logged. `symbol=None` pool fix still deferred. `graph/causal_graph.json` drifting uncommented again (2 nodes updated by runner).

**Last updated**: 2026-07-11T23:05Z — attended session; **PHASE 2b SHIPPED + DEPLOYED** (handoff `atlas-phase2b-scorer-2026-07-11`, commit cf76b7b, runner restarted 22:46:40Z, pushed, origin in sync). **The ledger now delivers, not just accumulates.** `score_due_predictions()` runs every cycle: when a bucket's window closes it replays the frozen strategy on realized data (fresh `since=` fetch, bypassing the stale main cache), writes a MODERATE-capped `live_observation` evidence record, and resolves the prediction append-only. **Verified live**: bucket 2948 (the 20 "expired unscored" predictions — recoverable, not lost) scored autonomously → **18 confirmed_null / 1 inconclusive / 1 edge_appeared, 19 moderate + 1 weak, 0 strong** (cap held → no spurious promotion). **evidence 253 → 273** (finally moving). `prediction.resolved` telemetry live. Bucket 2949 (20 open) will score autonomously when it resolves **2026-07-16** — no attended session needed. Tests 180 → **184**. Codex review filed (`.reviews/ledger-2b-scorer-2026-07-11.md`; findings pre-existing/guarded). — **SECONDARY (done)**: LAG TAG GAP **fixed** (`from_autocorrelation_signal` now emits `lag_N`; claim and strategy agree for new predictions). 2 stale URGENTs deleted (frozen-loop, unpushed-commits — both resolved). Branch pushed. — **NOTE**: the S3-P2 gate counts a scoring-only cycle as "empty" (no kill/promote/pivot), so it stays latched-silent while the loop is genuinely productive — cosmetic gap, harmless (no spurious URGENTs). **NEXT: 2c** = `atlas calibration` CLI (aggregate resolved outcomes/Brier). — *Prior context below.* Reflection T28 (2026-07-11T14:17Z) — since superseded: **NO ATTENDED SESSIONS** (~329h since last attended, 2026-06-28T04:08Z). **28th consecutive idle window.** Loop unchanged: `hypothesis_space_exhausted`, `evidence=253` frozen, `signals_found=22`, `skipped_not_promotable=5`, `consecutive_empty_count=~671` (+14 this window). **BUCKET 2948 EXPIRED UNSCORED** (confirmed). **BUCKET 2949 EXPIRES 2026-07-16T00:00:00Z** — 20 open predictions; Phase 2b must ship before Jul 16 or second window lost (~105h). **BUCKET 2950**: resolve 2026-07-23T00:00:00Z, `open_total=60`. **`skipped_unreplayable: 2` every cycle** — 28th window unresolved. **LAG TAG GAP**: 40 predictions lack `lag_N` tags — past-due since 2026-07-09. **STALE URGENTS (28th carry-forward)**: deletable. **BRANCH 7 AHEAD of origin** (reflect-only commits). S3-P2 gate permanently silenced (`emitted_for_current_streak: true`, streak=~671). **CRITICAL: Phase 2b must ship before 2026-07-16 — ~105h.**

**Previous (2026-07-11T02:20Z)**: Idle window. ~12 cycles; consecutive_empty_count 645→657. No attended sessions (~317h). Evidence=253 frozen. Bucket 2948 EXPIRED UNSCORED. Bucket 2949 at ~5 days. Lag tag: 27th carry-forward. Stale URGENTs: 27th carry-forward. Branch 6 ahead of origin.

**Previous (2026-07-10T14:22Z)**: Idle window. ~11 cycles; consecutive_empty_count 645→657. No attended sessions (~305h). Evidence=253 frozen. Bucket 2948 EXPIRED UNSCORED. Bucket 2949 at ~5.5 days. Lag tag: 26th carry-forward. Stale URGENTs: 26th carry-forward. Branch 5 ahead of origin.

**Previous (2026-07-10T02:19Z)**: Idle window. ~12 cycles; consecutive_empty_count 622→634. No attended sessions (~293h). Evidence=253 frozen. Bucket 2948 EXPIRED UNSCORED. Bucket 2949 at ~6 days. Lag tag: 25th carry-forward. Stale URGENTs: 25th carry-forward. Branch 4 ahead of origin.

**Previous (2026-07-09T14:17Z)**: Idle window. ~12 cycles; consecutive_empty_count 610→622. No attended sessions (~282h). Evidence=253 frozen. Bucket 2948 EXPIRED UNSCORED (resolve_ts passed Jul 9). Bucket 2949 at ~7 days. Lag tag: 24th carry-forward. Stale URGENTs: 24th carry-forward. Branch 3 ahead of origin.

**Previous (2026-07-09T02:18Z)**: Idle window. ~12 cycles; consecutive_empty_count 598→610. No attended sessions (~270h). Evidence=253 frozen. Bucket 2948 EXPIRED UNSCORED (resolve_ts passed at 00:00Z). Lag tag: 23rd carry-forward. Stale URGENTs: 23rd carry-forward. Branch 2 ahead of origin.

**Previous (2026-07-08T14:21Z)**: Idle window. ~12 cycles; consecutive_empty_count 586→598. No attended sessions (~258h). Evidence=253 frozen. Bucket 2948 at ~9.6h (last reflection before window closed). Lag tag: 22nd carry-forward. Stale URGENTs: 22nd carry-forward. Branch 20 ahead of origin.

**Previous (2026-07-08T02:20Z)**: Idle window. ~12 cycles; consecutive_empty_count 574→586. No attended sessions (~246h). Evidence=253 frozen. Bucket 2948 at ~21.7h. Lag tag: 21st carry-forward. Stale URGENTs: 21st carry-forward. Branch 19 ahead of origin.

**Previous (2026-07-07T02:21Z)**: Idle window. ~12 cycles (midnight rotation hid ~10 from events.jsonl; consecutive_empty_count 550→562 confirms). No attended sessions (~216h). Evidence=253 frozen. Bucket 2948 at ~45.6h. Lag tag: 19th carry-forward. Stale URGENTs: 19th carry-forward. Branch 17 ahead of origin.

**Previous (2026-07-06T14:20Z)**: Idle window. ~11 cycles (midnight rotation hid ~9 from events.jsonl; consecutive_empty_count 539→550 confirms). No attended sessions (~204h). Evidence=253 frozen. Bucket 2948 at ~57.7h. Lag tag: 18th carry-forward. Stale URGENTs: 18th carry-forward. Branch 16 ahead of origin.

**Previous (2026-07-05T14:19Z)**: Idle window. 12 cycles, all `hypothesis_space_exhausted`. No attended sessions (~178h). Evidence=253 frozen, consecutive_empty_count=527. Bucket 2948 at ~81.7h. Lag tag: 16th carry-forward. Stale URGENTs: 16th carry-forward. Branch 14 ahead of origin.

**Previous (2026-07-05T02:19Z)**: Idle window. 12 cycles, all `hypothesis_space_exhausted`. No attended sessions (~166h). Evidence=253 frozen, consecutive_empty_count=~515. Bucket 2948 at ~93.7h. Lag tag: 15th carry-forward. Stale URGENTs: 15th carry-forward. Branch 13 ahead of origin.

**Previous (2026-07-04T14:17Z)**: Idle window. 12 cycles, all `hypothesis_space_exhausted`. No attended sessions (~154h). Evidence=253 frozen, consecutive_empty_count=~503. Bucket 2948 at 4d 10h. Lag tag: 14th carry-forward. Stale URGENTs: 14th carry-forward. Branch 12 ahead of origin.

**Previous (2026-07-04T02:19Z)**: Idle window. 12 cycles, all `hypothesis_space_exhausted`. No attended sessions (~142h). Evidence=253 frozen, consecutive_empty_count=~491. Bucket 2948 at 4d 22h. Lag tag: 13th carry-forward. Stale URGENTs: 13th carry-forward. Branch 11 ahead of origin.

**Previous (2026-07-03T14:18Z)**: Idle window. 12 cycles, all `hypothesis_space_exhausted`. No attended sessions (~130h). Evidence=253 frozen, consecutive_empty_count=~479. Bucket 2948 at 5d 9h. Lag tag: 12th carry-forward. Stale URGENTs: 12th carry-forward. Branch 10 ahead of origin.

**Previous (2026-06-28T05:10Z)**: Attended session shipped Phase 1 (strip confounder-search theater, graph 73→69, tests 172→173) + Phase 2a (forward-prediction ledger, 20 predictions/cycle, tests 173→180). Routing fix: escalation URGENTs now route to supervisor/handoffs/INBOX/. Evidence=253 (frozen by design; 2b scoring starts 2026-07-09). Runner live with healthy event sequence: prediction.registered every cycle.

**Previous (2026-06-27T14:21Z)**: Reflection loop restored after 7-day 401 blind period. No attended sessions; ~189 all-continue cycles. evidence=253 (frozen, 16th+ window). consecutive_empty_count=329. URGENT ~378h. P2 at 21st carry-forward. graph drift 138 lines. 17 commits unpushed.

**Previous (2026-06-20T02:21Z)**: No attended sessions. 2 all-continue cycles (00:31Z, 01:31Z). evidence=253 (frozen, 14th window), nodes=73, edges=4. consecutive_empty_count=~140. URGENT ~198h old. P2 at 20th carry-forward. graph drift 138 lines. 16 commits unpushed. Synthesis Proposal 4 may not be firing.

**Previous (2026-06-19T14:18Z)**: No attended sessions. ~12 all-continue cycles. evidence=253 (frozen, 13th window), nodes=73, edges=4. consecutive_empty_count=138. URGENT ~186h old. P2 at 19th carry-forward. graph drift 138 lines. 15 commits unpushed.

**Previous (2026-06-19T02:19Z)**: No attended sessions. ~12 all-continue cycles. `{continue: 5}`, evidence=253 (frozen, 12th window), nodes=73, edges=4. consecutive_empty_count=126. URGENT ~174h old. P2 at 18th carry-forward. graph drift 138 lines. 14 commits unpushed.

**Previous (2026-06-18T14:19Z)**: No attended sessions. ~11 all-continue cycles. `{continue: 5}`, evidence=253 (frozen, 11th window), nodes=73, edges=4. consecutive_empty_count=114. URGENT ~162h old. P2 at 17th carry-forward. graph drift 138 lines. 13 commits unpushed.

**Previous (2026-06-17T14:17Z)**: No attended sessions. ~12 all-continue cycles. `{continue: 5}`, evidence=253 (frozen, 9th window), nodes=73, edges=4. consecutive_empty_count=91. URGENT ~138h old. P2 at 15th carry-forward. graph drift 138 lines. 11 commits unpushed.

**Previous (2026-06-16T14:17Z)**: No attended sessions. ~4 all-continue cycles. `{continue: 5}`, evidence=253 (frozen, 7th window), nodes=73, edges=4. consecutive_empty_count=67. URGENT ~114h old. P2 at 13th carry-forward. graph drift 138 lines. 9 commits unpushed.

**Previous (2026-06-16T02:21Z)**: No attended sessions. ~12 all-continue cycles. `{continue: 5}`, evidence=253 (frozen), nodes=73, edges=4. consecutive_empty_count=55. URGENT 106h old. P2 at 12th carry-forward. graph drift 138 lines. 8 commits unpushed.

**Previous (2026-06-15T14:19Z)**: No attended sessions. 4 confirmed cycles. All `{continue: 5}`, evidence=253 (frozen), nodes=73, edges=4. consecutive_empty_count=43. URGENT 93h old. P2 at 11th carry-forward. graph drift 138 lines. 7 commits unpushed.

**Previous (2026-06-15T02:17Z)**: No attended sessions. 2 confirmed cycles (15:53Z, 16:54Z). All `{continue: 5}`, evidence=253 (frozen), nodes=73, edges=4. consecutive_empty_count=31. URGENT 81h old. P2 at 10th carry-forward. graph drift 138 lines. 6 commits unpushed.

**Previous (2026-06-14T14:19Z)**: No attended sessions. 12 cycles (02:46Z–13:50Z), all `{continue: 5}`, evidence=253 (frozen), nodes=73, edges=4. consecutive_empty_count ~19. URGENT 66h old. P2 at 9th carry-forward. graph drift 138 lines. 5 commits unpushed.

**Previous (2026-06-14T02:21Z)**: No attended sessions. 2 cycles ran (23:32Z, 00:38Z), both `{continue: 5}`, evidence=253 (frozen), nodes=73, edges=4. consecutive_empty_count=7 (RESET from 761919e kill). TESTING count=0. URGENT 54h old. P2 at 8th carry-forward. graph drift 138 lines. 4 commits unpushed.

**Previous (2026-06-13T14:21Z)**: No attended sessions; 14 cycles all-continue; evidence=252 (frozen); consecutive_empty_count=44; frozen-loop URGENT 42h old; P2 at 7th carry-forward; graph drift ~104 lines.

**Previous (2026-06-13T02:18Z)**: No attended sessions; 2+ cycles all-continue; evidence 252 (+1 weak); graph dirty (3 runner-written uncommitted nodes); frozen-loop URGENT 30h old; P2 at 6th carry-forward.

**Previous (2026-06-12T14:21Z)**: No attended sessions; 12 cycles all-continue; evidence 251; graph dirty (3 runner-written uncommitted nodes); P2 at 5th carry-forward.

**Previous (2026-06-10T14:20Z)**: 3 commits not pushed; evidence frozen at 244; 2nd consecutive push-blocker; loop idle.

**Previous (2026-06-09T16:45Z)**: **ADR-0035 implementation shipped + deployed**: falsified claims are now first-class causal-map content. `graph/causal_graph.json` backfilled with 69 refuted nodes. `from_graph_gaps()` now generates follow-up confounder-search hypotheses. `atlas-runner.service` restarted at 2026-06-09T16:43Z.

---

## Deployed / running state
- **Mode**: autonomous research loop (signal intake → hypothesis → experiment → evidence → graph update). **RUNNING** since 2026-06-09T16:43Z after ADR-0035 migration/restart. Per principal clarification 2026-06-09, **keep it running** unless a concrete safety/cost issue arises; any pause is a principal-facing decision with evidence, not an idle-cycle cleanup.
- **Lifecycle classification**: **research-only** (snapshot 2026-04-25T19:30Z). Live verdict: `.venv/bin/atlas strategy readiness`. Promoted primitives = 0 → live-signal generation is blocked by absence of primitives. Promotable candidates = 0. Next milestone per `atlas-strategy-readiness-2026-04-25.md` is paper-strategy materialization from promoted primitives (no execution layer until then).
- **Domain**: crypto markets (Bitstamp for deep OHLCV history — Binance/Bybit blocked on Hetzner US server).
- **Entry**: production = `systemctl status/start/stop atlas-runner.service`. Debug = `.venv/bin/atlas run --once` from project root.
- **Service unit**: `/etc/systemd/system/atlas-runner.service`; mirrored copy in repo at `deploy/atlas-runner.service` for re-installation. Re-install with `sudo install -m644 deploy/atlas-runner.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now atlas-runner.service`.
- **Data stores**: `methodology.jsonl`, `pending_revalidation.jsonl`, `graph/`, `.atlas/`, `.canon/`.

## What just shipped
- **ADR-0035 falsifications-as-map-content (2026-06-09T16:45Z, this commit, deployed)**:
  - `models/graph.py` now supports mixed-status graph nodes. Promoted primitives remain `status=promoted`, `trust=high`; falsified hypotheses become `status=refuted`, `trust=tested_refutation` and do **not** count as promoted primitives or trading-ready signals.
  - New `graph_backfill.py` helper and `atlas graph backfill-falsified` CLI project existing FALSIFIED hypotheses into the graph. Live backfill added 69 refuted nodes, 0 edges, 7 skipped non-falsified records.
  - `from_graph_gaps()` can generate follow-up hypotheses from refuted roots: "the refuted claim failed because of an unmodeled market regime or confounder..." tagged `graph_gap/refuted_claim/confounder_search`.
  - Runner writes future kills into the causal map and emits structured empty-cycle telemetry (`no_action_reason=hypothesis_space_exhausted`, `refuted_nodes`, `backfill`).
  - Adversarial review (`supervisor/.reviews/atlas-falsified-map-content-2026-06-09.md`) flagged claim-fidelity risk. Fixed before commit: graph-gap hypotheses require claim-faithful parsed datasets and no longer fall back to arbitrary BTC/ETH default cross-validation.
  - Manual validation: `timeout 240 .venv/bin/atlas run --once` generated graph-gap hypotheses and evidence instead of the previous empty cycle, then timed out before full cycle completion. Follow-up fix: graph-gap hypotheses skipped for `no_claim_faithful_dataset` no longer create new active cycles. Remaining caveat: pre-existing/manual-validation active-cycle ambiguity remains (`atlas status` warns multiple active cycles); do not treat historical cycle cleanup as solved by this patch.
  - Tests: 168 → 172. `.venv/bin/python -m pytest` → 172 passed, 20 warnings (pre-existing numerical warnings in min-bars guard tests).
- **P1 TESTING re-eval loop (2026-05-02T17:05Z, commit 71224e9) — PUSHED + DEPLOYED 2026-05-02T17:04:56Z**:
  - `_include_orphaned_testing` runs before `_top_up_from_formulated_pool` in `run_cycle`. Ordering enforced by source-inspection test (reversed, top-up fills slots and TESTING starves forever).
  - `_has_productive_universe_dataset` gate: requires ≥ MIN_BARS_FOR_RESEARCH bars on at least one unfresh DEFAULT_UNIVERSE pair before re-including. SOL/USDT 1h (0 bars on Bitstamp) correctly skipped.
  - Claim-infeasible hygiene: TESTING hypotheses with permanently-infeasible claims are skipped but NOT auto-migrated (out of scope for re-eval path).
  - Telemetry: `cycle.testing_reeval` with 3 counters (`re_included_productive`, `skipped_no_productive_dataset`, `skipped_claim_infeasible`).
  - Tests: 156 → 168 (+12 in `tests/test_auto_top_up.py`). Adversarial review via subagent fallback; codex CLI unavailable; disclosed in commit.
  - **Delivery proof**: service uptime since 17:04:56Z May 2 (matches commit timestamp 17:04:50Z); `_include_orphaned_testing` importable on `from atlas.runner import AutonomousRunner`; observed TESTING 7→0 transition with +14 evidence and +7 falsified between deploy and 2026-05-04T14Z (the P1 re-eval cycles ran the orphans against unfresh universe pairs as designed; all 7 hit the all-weak-or-negative kill threshold).
- **S3-P2 rotation-safe counter (2026-05-02T02:11Z, commit 39b6d2f) — DEPLOYED (2026-05-02T14:25:28Z)**:
  - **Root cause fixed**: `_read_recent_runner_events()` removed entirely. After midnight UTC rotation, the Apr 29 kill event was only visible in a gzip archive; `broken_since_last` found no kill and suppressed the gate indefinitely on what were genuinely new post-kill empty cycles.
  - **Fix**: persistent `consecutive_empty_count` in `.atlas/escalation_state.json`. `_update_streak_counter()` increments on every empty/all-continue cycle, resets to 0 on any decisive cycle (kill/promote/pivot). `_maybe_escalate_frozen_loop` reads only the state file — midnight rotation cannot affect it.
  - **Migration**: old state file format (`last_streak_start_ts`/`last_emitted_ts`) has no recognized new fields → `_load_escalation_state` returns `{}` → counter starts at 0 → gate re-arms after 3 new empty cycles (~3h at hourly cadence).
  - **Tests**: 5 new unit tests for `_update_streak_counter` + regression `test_rotation_proof_counter_persists_across_events_wipe`. 24/24 gate tests pass, 156/156 total.
  - **CLAUDE.md**: P2 rule added — `_maybe_escalate_frozen_loop` requires `adversarial-review.sh` before any commit (7 bug classes, 6 commits). Rule and code land in same commit (39b6d2f).
  - **Review gap**: Codex unavailable; `adversarial-review.sh` blocked; `advisor()` consulted as fallback. Disclosed explicitly in commit message.
  - **Deployment**: restarted by attended session (Opus 4.7, 2dd59ae) at 14:25:28Z May 2. Confirmed live: `cycle.escalated consecutive_cycles=3` fired at 00:32Z May 3.
- **A+C+D2 pool-rotation (2026-05-01)** — principal-authorized via `atlas-pool-rotation-decision.md`. Closes the 90+h frozen-loop blocker:
  - **A (auto-top-up)**: `runner.py::_top_up_from_formulated_pool` promotes feasible FORMULATED hypotheses to TESTING when `generate_hypotheses` under-fills the cycle. Single code path; A and D2 are the same operation viewed from two symptoms.
  - **C (BitMEX migration)**: `10dc7fca3973e82a` and `4fdf3a65763ab083` migrated to status=INFEASIBLE via inline state-store edit. They no longer occupy slots in the loop's selection or block evaluation.
  - **D2 (STRICT, with reviewer-fix)**: `_data_currently_available` requires explicit (symbol, timeframe) ∈ `DEFAULT_UNIVERSE` AND `fetch_ohlcv` ≥ `MIN_BARS_FOR_RESEARCH` bars. **Adversarial-review surfaced a one-way-door bug in the original**: original predicate marked off-universe / insufficient-bars as INFEASIBLE, which would have permanently locked out hypotheses whose feasibility is environmental (e.g. SOL/USDT 1h gaining bars over time). Refactored to two predicates: `_claim_is_permanently_infeasible` (claim names a geo-blocked exchange — one-way) vs `_data_currently_available` (reversible). Environmental skips leave hypothesis FORMULATED.
  - **Telemetry**: new `cycle.top_up` event with `promoted`/`infeasible`/`skipped_not_promotable`/`pool_size`/`current_size`. Always emits when pool is non-empty so the frozen-loop monitor can't go blind to "pool full of stuck-but-not-INFEASIBLE" failure mode.
  - **Bonferroni**: recomputed in `run_cycle` after top-up so n_tests reflects the post-top-up cycle size, not the pre-top-up generate count.
  - Tests: +21 in `tests/test_auto_top_up.py` covering tag parser, both predicates, top-up promotion/infeasibility/environmental-skip semantics, telemetry, methodology log. 130 → 151 total.
  - Adversarial review: subagent (codex CLI unavailable). 4 must-fix found; 1 acted on (one-way-door semantics — implemented above), 3 deferred or already considered. Findings logged in conversation transcript.
- **S3-P2 gate fix #2 — rotation-safe dedup (2026-04-27T02:40Z) — PUSHED (commit ee9beaf) + DEPLOYED**: dedup now persists to `.atlas/escalation_state.json` (atomic write) and uses a semantic check ("has any non-continue cycle.completed appeared since last_emitted_ts?") instead of a streak-start timestamp comparison. The earlier timestamp form survived in-memory streak growth (commit 34f4a83) but was incidentally broken by midnight telemetry rotation: the post-rotation events.jsonl no longer contains prior cycle.escalated events, and the post-rotation visible streak start drifted later than the true streak start. State file seeded with the legitimate prior emission (21:30Z 04-26) so the post-deploy gate doesn't fire spuriously. +1 regression test simulating telemetry rotation. Tests 124 → 125.
- **S3-P2 gate dedup fix (2026-04-26T02:41Z) — PUSHED (commit 34f4a83) + DEPLOYED**: walk-back now covers the entire streak instead of stopping at `FROZEN_LOOP_ESCALATION_AFTER`. Bug surfaced at 02:37Z when the gate re-fired on a streak that had not broken since 17:12Z 04-25 — `streak_start_ts` had drifted forward as the streak grew past the threshold, eventually outpacing the prior escalation's emit timestamp and defeating the dedup check. +2 regression tests cover both "streak grows past threshold" (must NOT re-emit) and "kill resets, new streak forms" (MUST re-emit). Tests 122 → 124. The duplicate `URGENT-atlas-frozen-loop-2026-04-26T02-37Z.md` was deleted; the legitimate prior escalation (`general-atlas-frozen-loop-diagnosis-2026-04-25T21-40Z.md`) still represents the open principal-class tuning question.
- **Strategy-readiness CLI + S3-P2 escalation gate (2026-04-25T19:30Z) — PUSHED (commit 90bd5fc) + DEPLOYED (service restart 2026-04-25T19:27:30Z)**:
  - `atlas strategy readiness` — one-screen verdict: classification (research-only / strategy-candidate / paper-trading-ready / live-capital-ready), promoted primitive count, promotable candidate count (mechanical: passes promotion gate now), evidence distribution (quality/direction), all-continue streak from telemetry. Backed by store + telemetry, not hand-written state.
  - `runner.py::_maybe_escalate_frozen_loop` — after `FROZEN_LOOP_ESCALATION_AFTER = 3` consecutive cycle.completed events whose `decisions_by_kind == {"continue": N}` (vacuous cycles skipped, not counted), emits `cycle.escalated` and writes one URGENT handoff to `runtime/.handoff/URGENT-atlas-frozen-loop-<iso>.md`. Idempotent (won't re-emit until streak breaks); URGENT handoff dedup via glob.
  - `evaluate_promotion_gate(evidence)` extracted as a module-level pure predicate so the CLI and the runner share one source of truth — no parallel reimplementation.
- **Frozen-loop fix deployed + verified (2026-04-25T15:58Z)**: bf6fc4e pushed and `atlas-runner.service` restarted at 15:45:12Z. First post-restart cycle.completed: `{decisions_by_kind: {kill: 5}, total_evidence_store_size: 143, signals_found: 22}`. Five hypotheses correctly falsified with fresh evidence (was 5 × continue, evidence frozen at 133).
- **`--allow-merge` gate on `migrate_claim_hash.py` (commit 4977ad9)**: per `URGENT-atlas-migration-merge-collapse`. Merge groups now abort the migration with `SystemExit(2)` and a per-field divergence audit. Audit of current `.atlas/hypotheses/`: 59 records, 0 with `claim_variants` populated → no prior runs ever silently merged anything. Tests: 109 → 111.
- **Deploy-push gate (commit 0fedaf2)**: `deploy/README.md` documents the rule (push+restart OR `code_landed_NOT_deployed` note in CURRENT_STATE.md). `scripts/deploy-check.sh` is a non-blocking diagnostic for unpushed-commits + service-vs-commit-time skew.
- **`cycle.completed` telemetry (2026-04-24T15:37Z, commit 66a3db7)**: `runner.py` emits `cycle.completed` on the happy path with `decisions_by_kind`, `signals_found`, `graph_nodes`, `graph_edges`, `total_evidence_store_size`. First post-deploy emission confirmed all-continue frozen-loop state is now directly visible in telemetry.

## Known broken or degraded

- ~~**RUNNER STUCK (was 6th window)**~~ — **RESOLVED 2026-05-04T14:21Z (reflection confirmation)**. P1 (`_include_orphaned_testing`, commit 71224e9) was deployed at 2026-05-02T17:04:56Z — empirically confirmed via service uptime, method importability, +7 FALSIFIED behavioral signature. Loop is **legitimately idle**: TESTING=0 (P1 cleared orphans), FORMULATED=5 (all blocked under STRICT-D2). No service restart needed. — ~~**STALE URGENT deleted 2026-05-07T02:21–14:17Z**~~: `URGENT-atlas-frozen-loop-2026-05-02T14-18-55Z.md` removed. S3-P2 secondary (glob) gate unblocked. Primary gate (`emitted_for_current_streak: true` in `.atlas/escalation_state.json`) remains locked — resets only on a decisive research outcome (kill/promote/pivot). No active URGENT on disk; loop at 111 cycles without an escalation artifact.
- ~~**RUNNER STUCK — two independent blockers**~~ — **RESOLVED 2026-05-01 via A+C+D2 deploy** (see "What just shipped"). (1) Two BitMEX hypotheses migrated to INFEASIBLE; (2) signal-hash-drift bypassed by auto-top-up promoting FORMULATED hypotheses directly when signal scan under-fills the cycle. Pool will deplete fast under STRICT-D2 (parameter drift means promoted hypotheses are likely to falsify) — that is the expected and desired behavior; new signal scans plus the existing graph-gap generator are responsible for replenishing the pool. Watch `cycle.top_up` telemetry to confirm replenishment cadence.
- ~~**S3-P2 gate undeployed**~~ — **DEPLOYED 2026-05-02T14:25Z** (service restart via 2dd59ae). Counter gate confirmed live: `cycle.escalated consecutive_cycles=3` fired at 00:32Z May 3.
- ~~**Runner selects `formulated` hypotheses; `status=testing` never set on selection**~~ — **RESOLVED 2026-05-01**: `_top_up_from_formulated_pool` now sets `status=TESTING` explicitly when promoting from the FORMULATED pool. BitMEX orphans migrated to INFEASIBLE.
- **Test count** — 180 after 2026-06-28 attended session. No new tests since.
- **TESTING count = 0** — Runner evaluates 5 FORMULATED-status hypotheses (all symbol=None). Skip path does not persist TESTING status. Loop does zero productive work. Root cause: P2 unfix (see What the next agent must read first).
- ~~**State file timestamp anomaly**~~ — **Resolved 2026-04-27T17:00Z**: my original seed had a 14-hour math error (used 07:30Z when I claimed 21:30Z). Re-seeded with verified values from the 04-27 02:36:44Z emission visible in current events.jsonl: `{"last_streak_start_ts": 1777250052457, "last_emitted_ts": 1777257404561}`. Gate is now correctly anchored.
- **Concurrent runner safety** (known soft edge, not URGENT): `_maybe_escalate_frozen_loop` read-check-write is not atomic. A parallel `atlas run --once` debug session running alongside the live service could double-emit. Worst case is 2 telemetry events + 1 URGENT file (handoff dedup wins eventually). flock would close it; tracked but deferred per the 17:00Z review.
- **Cache-vs-gate misalignment** (open, principal-class): `DATASET_RETEST_AFTER = 1 day` and `FROZEN_LOOP_ESCALATION_AFTER = 3 cycles` interact such that the gate fires roughly once per 24h between productive cycles. The gate firing is correct epistemic signal (the loop genuinely cannot promote during the cache window), but produces a recurring URGENT. Tuning options A–D documented in `general-atlas-frozen-loop-diagnosis-2026-04-25T21-40Z.md`. No code change without principal direction. Confirmed cadence via 04-26 18:14Z kill (evidence 153→163) → 21:30Z escalation (3-cycle new streak); the dedup-fixed gate is working precisely as documented.
- **Telemetry pollution (cosmetic)**: 4 `cycle.escalated` events in `events.jsonl` from initial test runs before `_emit_telemetry` was refactored to honor `self.TELEMETRY_PATH`. Bogus markers (`streak_start_ts=1000`, `evidence=0`); harmless to gate logic. Not scrubbing the shared file.
- ~~**Evidence accumulation frozen at 133**~~ — **Resolved 2026-04-25T15:58Z**: bf6fc4e pushed and service restarted. Post-restart cycle.completed shows `{kill: 5}` with `total_evidence_store_size: 143`. The freshness fix is live and producing correct falsifications.
- ~~**No `cycle.completed` event**~~ — **Fixed 2026-04-24T15:37Z (commit 66a3db7)**: `runner.py` now emits `cycle.completed` on the happy path with `decisions_by_kind` payload. First post-deploy emission confirmed `{"continue": 5}` across 5 hypotheses with `total_evidence_store_size=133` — the all-continue frozen-loop state is now directly visible in telemetry. (`cycle.failed` already existed at line 975.)
- **FOUR COMMITS NOT PUSHED — URGENT FILED (P1, 3rd consecutive reflection)**: `b0df455`, `8249acc`, `c6d7288`, `6a7e266` deployed locally but absent from `origin/main`. URGENT handoff at `runtime/.handoff/URGENT-atlas-unpushed-commits-3rd-cycle.md`. `git push origin main` is a one-command fix. ADR-0035 code (b0df455+8249acc) runs the live service — a hard reset would revert it.
- **Evidence 247 (slowly accumulating, all weak)**: 3 records added in last 12h from non-skipping graph-gap hypotheses (13aac1faf, 2a58c3f4, 8c19e8b9). All produce weak-only evidence → continue. 2 hypotheses (b612deba, dd50f9b9) skip with `no_claim_faithful_dataset` — claim text parse fails because `symbol=None` stored in state store. Graph: 69 nodes / 0 edges unchanged. No decisive cycles possible under current hypothesis pool.
- **`/review` EROFS** still blocks; workaround via `adversarial-review.sh` in use.
- ~~**Two hypotheses stuck in `testing` indefinitely**~~ — **RESOLVED 2026-05-01** via INFEASIBLE migration (see A+C+D2 deploy).
- ~~**Hypothesis pool rotation via signal scanner only**~~ — **RESOLVED 2026-05-01** via A+C+D2 auto-top-up. Pool trajectory now: replenishment via signal scan + graph-gap generator; depletion via auto-top-up promotion + downstream falsification. Watch `cycle.top_up.skipped_not_promotable` count for off-universe / insufficient-bars accumulation that would indicate a pool-replenishment vs signal-drift mismatch.

### Autonomous loop deployed via systemd (2026-04-24T12:27Z) — UNCOMMITTED
Per principal authorization on `atlas-autonomous-loop-deploy-2026-04-24T12-40Z` handoff. Atlas now runs as a persistent systemd service:

- **Unit**: `/etc/systemd/system/atlas-runner.service` — `Type=simple`, runs `.venv/bin/atlas run --interval 3600` as root from `/opt/workspace/projects/atlas`, `Restart=on-failure` with `RestartSec=300`, `StartLimitBurst=3` per `StartLimitIntervalSec=3600` so a startup bug can't burn Bitstamp quota in tight loops.
- **Repo copy**: `deploy/atlas-runner.service` — same content, tracked in git for re-deployment after host re-image.
- **State**: `active (running)` since `2026-04-24 12:27:52 UTC`. PID 587285.
- **Telemetry**: `cycle.started` and `hypothesis.decided` events landing in `/opt/workspace/runtime/.telemetry/events.jsonl` with `sourceType=system`. SOL/USDT correctly skipped this cycle (`MIN_BARS_FOR_RESEARCH` guard fired with 0 bars returned by Bitstamp for that symbol).
- **Closes**: `URGENT-atlas-loop-not-running-2026-04-24.md` (5-day silence resolved).

### Canon adapter + migration gap closure (2026-04-23T17Z) — PUSHED (commit d81681a)
Session executed the 4-item `atlas-canon-gap-fixes-2026-04-23T17-05Z.md` handoff:

- **Decision backfill** — `src/atlas/adapters/discovery/migrate.py` now emits Decision envelopes for FALSIFIED hypotheses (kind=`kill`, deterministic id `dec-{hyp_id}-kill`). 40 Decision envelopes written to `.canon/decisions/` on this session's re-run.
- **Transactional claim-hash migration** — `scripts/migrate_claim_hash.py` refactored into `run_migration()` with a two-phase-commit ordering: Phases 2W and 3W write new-id files without unlinking; Phases 4 and 5 re-link experiments and evidence; Phase D deletes deferred old files only after re-links complete. Crash between Phases 4–5 and D is recoverable by re-run — covered by new `test_claim_hash_migration.py`.
- **`sources=` parameter** — `_common_envelope()` and every `emit_*` function now accept `sources` kwarg (default `[]`). When atlas starts citing canon, callers pass real SourceRefs instead of the hardcoded empty list that would have produced false first-party provenance.
- **SOL min-bars guard** — `runner.py` adds `MIN_BARS_FOR_RESEARCH = 833` (walk-forward minimum). `scan_signals()` skips any symbol with fewer bars and emits a methodology log entry so the skip is visible in telemetry. Cross-asset pairing also respects the gate.

**Canon backfill re-run counts**: 59 claims / 133 evidence / 40 decisions / 82 events / 1 policy. The handoff's acceptance numbers (47/123/40/82/1) reflected the 2026-04-19 snapshot; counts are higher now because live-run activity since then added 12 hypotheses + 10 evidence records. Decisions and events match handoff exactly.

**Adversarial review** (`supervisor/.reviews/atlas-migration-reorder-2026-04-23T17-13Z.md`) on the migration reorder raised three findings, all pre-existing behaviors of the merge path (not introduced by this session): (1) merge groups silently collapse colliding hypotheses on fields other than `claim`; (2) unconditional overwrites let a stale canonical file be clobbered on re-run; (3) re-link scope covers only `hypothesis_id`/`hyp_id` — graph store and methodology log are not rewritten. The handoff's scoped ask was the Phase-3-after-4-5 reorder; these are separately tracked.

Tests: 97 → **107/107** passing (+5 canon adapter, +3 migration, +2 min-bars).

### URGENT carry-forward resolution (2026-04-20T17Z) — PUSHED (commit 2004911)
Session resolved both items on the URGENT handoff that had breached the 3-cycle carry-forward threshold:
- **Telemetry rename**: `runner.py:914` `evidence_count` → `total_evidence_store_size`. Field name now accurately describes what it reports (total store size, not per-cycle count). 97/97 tests still pass.
- **Canon adapter adversarial review**: `.reviews/1d627c3-canon-adapter-review-2026-04-20T17Z.md`. Codex (gpt-5.4) flagged three issues. See Open Items.

### Exchange + timeframe fix (commit 13601d2, 2026-04-19 14:52 UTC) — PUSHED
Attended session `c5472d70` (Opus 4.6) fixed the structural blocker that kept all hypotheses stuck at "continue" for 4+ reflection cycles:
- **Root cause**: CLI defaulted to Kraken (`--exchange kraken`), which caps OHLCV at ~720 bars regardless of `since` parameter. `market.py` was designed for Bitstamp's deep pagination (99K+ 1h bars from 2015).
- **Fix**: Changed CLI default exchange to `bitstamp` (aligns with `market.py` design and runner's own default). Removed 4h from DEFAULT_UNIVERSE (1h only: BTC, ETH, SOL). Updated two hardcoded 4h references. Made `_BITSTAMP_SYMBOLS` mapping conditional on exchange.
- **Result**: `atlas run --once` completed with 5 hypotheses tested, 10 experiments, real walk-forward OOS stats. 4 hypotheses found strong contradictions (correctly falsified). 1 hypothesis (weekend volatility) weak/inconclusive → continues.
- **SOL gap**: SOL/USDT on Bitstamp produced no signals during scan (data available but possibly too short for signal detection). Effectively 2 datasets (BTC, ETH), not 3.

### Canon adapter + backfill (commit 1d627c3, 2026-04-19 04:19 UTC) — PUSHED
Workspace executive session `847b6afa` (Opus 4.7) implemented the L1 discovery-framework adapter per ADR-0026 and agentstack plan `calm-squishing-peacock.md`. Components:
- `src/atlas/adapters/discovery/emit.py` (475 LOC) — `emit_claim`, `emit_evidence`, `emit_decision`, `emit_event_log`, `emit_policy_tier_mapping`
- `src/atlas/adapters/discovery/migrate.py` (253 LOC) — one-shot backfill with JSON Schema validation
- `src/atlas/adapters/discovery/MAPPING.md` — documents lossy atlas.quality → canon.tier mapping
- `tests/test_canon_adapter.py` — 16 new tests; total now **97/97**
- `.canon/` backfill: 47 claims, 123 evidence, 82 event_log, 1 policy, **0 decisions**

**Known gap**: `migrate.py` never calls `emit_decision()`. The 40 falsified hypotheses have no Decision records in `.canon/decisions/`. The function exists in `emit.py` but is not called by the migration script.

**Architectural note**: this commit was authored by the executive session, violating the workspace convention (exec sessions should not write project code directly). The adapter is correct and tested; but future refactors should route through an atlas project session.

### Codex adversarial review of 040c053 (commit a55cab0, 2026-04-18 ~22:51 UTC) — PUSHED
Post-hoc review of the canonical claim-hash migration (`040c053`). Review artifact at `.reviews/040c053-review-2026-04-18T22-51-16Z.md`. Three findings (see Open Items).

### Attended session (commits 040c053 + ea44220 + f82f020 + 21deba0, 2026-04-18 12–14 UTC)
Session c5472d70 (Opus 4.7) resolved all 4 pending handoffs and closed both URGENT escalations.

- **040c053** — Canonical claim-hash migration: 42 hypotheses re-keyed, 123 experiments + 123 evidence re-linked, schema v2.
- **ea44220** — Live path validated: `atlas run --once` succeeded. 5 hypotheses evaluated, all "continue" (4h data too short).
- **f82f020** — Removed stale context-repository canonical-objects reference from CLAUDE.md.
- **21deba0** — Opted CLAUDE.md into M4 ADR-0021 session-start context-load hook.

## Open items

### Canon adapter gap
- ~~**No Decision records backfilled**~~ — **Fixed 2026-04-23**: `migrate.py` now emits Decision envelopes (kind=`kill`) for FALSIFIED hypotheses. 40 decisions live in `.canon/decisions/`.

### Unresolved Codex findings (from a55cab0 review of 040c053)
- ~~**Non-transactional migration**~~ — **Fixed 2026-04-23**: `scripts/migrate_claim_hash.py` reordered to write-new-then-delete-old. Crash between re-link and delete is recoverable (covered by `tests/test_claim_hash_migration.py::test_crash_between_relink_and_delete_is_recoverable`).
- **Merge-on-canonical assumption** — `scripts/migrate_claim_hash.py` still auto-merges hypotheses that hash to the same canonical form with silent lossy consolidation of non-claim fields. Flagged in 2026-04-23 review as the highest-severity finding; not in scope for this session's reorder. No test covers merge scenario.
- **Evidence ID leakage** — post-migration re-ingest of old findings produces new `ev_id`s. Cosmetic but accumulates indefinitely.

### Unresolved Codex findings (from 2026-04-20 review of canon adapter 1d627c3)
- ~~**`sources=[]` hardcoded**~~ — **Fixed 2026-04-23**: `emit.py` emitters accept `sources=` kwarg; default `[]` preserves existing behavior, callers can now pass real SourceRefs.
- **No dual-write transaction** — emit_claim depends on `.atlas/hypotheses/<id>.json` existing to attach required artifacts (emit.py:193–202); StateStore.save only guarantees atomicity for the `.atlas` write. Currently moot (one-shot migration), but will bite when dual-write is added.
- **Adapter boundary already eroded** — `canon_dir()` creates directories (emit.py:48–54), emitters read/hash on-disk atlas files (emit.py:66–71, 193–199, 235–240), and migrate.py reaches into private helpers (migrate.py:31–37). Not a "pure projection layer" as docstring claims.

### Unresolved Codex findings (from 2026-04-23 review of migration reorder)
- **Destructive merge collapse** — merge groups arbitrarily keep the first sorted file as primary and preserve only alternate claim text in `claim_variants`; fields other than `claim` on the discarded hypotheses are silently lost. Blast radius = downstream analysis of rationale/tags/domain on consolidated hypotheses.
- **Overwrite on re-run is unconditional** — Phase 2W/3W writes do not check whether a canonical file already exists with divergent content. A manually-repaired artifact can be clobbered before Phase D deletes the old sources.
- **Re-link scope is narrow** — only `hypothesis_id`/`hyp_id` in experiments/evidence are rewritten. Graph store nodes, methodology-log entries, and cycle snapshots may still carry old IDs after a migration.

### Structural blockers
- **`/review` EROFS** — `/review` Claude skill still blocked by read-only mount on `/root/.claude.json`. Workaround `supervisor/scripts/lib/adversarial-review.sh` (codex-based) validated in this session. INBOX proposal `proposal-tick-prompt-adversarial-review-gate-2026-04-17T22-48Z.md` awaits attended session decision.

### Telemetry / methodology gaps
- ~~**`evidence_count` telemetry misleading**~~ — **Fixed 2026-04-20**: renamed to `total_evidence_store_size` at `runner.py:914`. Field name now matches behavior.
- **methodology.jsonl feedback loop structurally absent** — signal-source quality untracked.
- **`created_at` non-determinism in concurrent evidence writes**: cosmetic only.
- **Backtest ≠ live performance**: known limitation, Phase 2.

### SOL dataset gap
- ~~**SOL/USDT produces no signals**~~ — **Fixed 2026-04-23**: runner.py adds `MIN_BARS_FOR_RESEARCH = 833` guard. Short-history symbols are skipped with a methodology log entry instead of silently wasting Bonferroni budget. Future SOL history accumulation will automatically re-enable scanning once it crosses the floor.

## Blocked on
- `/review` EROFS is a system issue for the general session to resolve (INBOX proposal pending decision).

## Known gotchas
- `.venv/bin/pytest` shebang points to old path. Use `.venv/bin/python -m pytest`.
- `list_all()` in StateStore skips `.tmp` files — safe to have tmp files during concurrent writes.
- The migration script (`scripts/migrate_claim_hash.py`) is idempotent for no-merge runs only. If merge groups appear, the merge path is destructive on non-claim fields — gate with an explicit `--allow-merge` flag before running.
- Ingest-created evidence IDs embed `hyp_id` in their hash. Post-migration re-ingest produces a new ev_id — cosmetic, old record persists.
- Evidence `source_hash` is `""` on records created before c5b7a13 — correct, field is optional.
- **Canon adapter Decision coverage**: `.canon/decisions/` holds 40 `kill` Decision envelopes (one per FALSIFIED hypothesis). PROMOTED/SUPPORTED status does not today produce a Decision envelope — that path runs through the primitive promotion gate and is deliberately not backfilled. Re-run the adapter migration (`python -m atlas.adapters.discovery.migrate --atlas .`) after any `.atlas/` change to refresh.
- `emit_policy_tier_mapping()` in `emit.py` uses `datetime.now()` — every re-run of the migration produces a timestamp-drifted policy file, creating working-tree noise. Pass a pinned `emitted_at` value if determinism is needed.

## Recent decisions
- **2026-04-23 — M1+M2 retrofit (context-repo pattern pass 2)**: added frontmatter to 3 core files (CLAUDE.md, CURRENT_STATE.md, README.md), generated `index.md`, copied `scripts/build-index.sh` from context-repository (no modifications). 23 artifact-class files (`findings/`, `.reviews/`, `MAPPING.md`) left unindexed pending per-file frontmatter by domain-aware sessions. Known gap: reflections update CURRENT_STATE.md uncommitted until M5 enforcement ADR ships — spec §Known limitations L1 in practice, not a retrofit failure.
- **ADR-0026 (2026-04-19)**: agentstack chartered as third canon instance; atlas adapter shipped as first reference implementation. Adapter-first, L2 runtime extraction deferred.
- **Claim hash canonical: [:16] of SHA-256 with lowercase + ws-collapse + strip trailing punct**. `claim_canonical()` in `utils.py`. Schema v2.
- **Evidence ID**: `uuid4().hex[:12]` — NOT deterministic (prior belief was wrong; corrected 2026-04-25T02:17Z). The `source_hash` field is a content snapshot but does not serve as the ID.
- **StateStore writes are atomic**: tmpfile + os.replace. No explicit file locks.
- **Revalidation queue is append-only**: dedup-on-read, not dedup-on-write.
- **Pre-registered fields are immutable**: enforced in StateStore. Do not relax.
- **Live path validated (2026-04-19)**: `atlas run --once` with Bitstamp 1h data completed. 5 hypotheses tested, 10 experiments with walk-forward OOS stats. 4 found strong contradictions, 1 weak/inconclusive. System produces real falsification decisions.
- **Default exchange is Bitstamp (2026-04-19)**: Kraken caps OHLCV at ~720 bars regardless of `since` — below the 833-bar walk-forward minimum. Bitstamp provides 99K+ 1h bars via pagination.

## What the next agent must read first
0. **LOOP STATE: RUNNING + LEDGER ACTIVE — updated 2026-06-28T14:19Z (reflection)**. **(a) Phase 1+2a shipped + deployed 2026-06-28T04:08Z. (b) Telemetry healthy: `cycle.started → prediction.registered → cycle.top_up → cycle.completed` every ~1h. (c) Evidence=253 FROZEN (expected — 2b scoring not yet built; first window closes 2026-07-09). (d) Escalation routing FIXED (f24d298) — URGENTs now go to supervisor/handoffs/INBOX/. Gate still latched (`emitted_for_current_streak: true`); re-arms only after decisive cycle. (e) KNOWN GAP (sharpened): `from_autocorrelation_signal` emits lag in claim text but NOT in tags. All 40 existing predictions (buckets 2948+2949) lack `lag_N` tags. 2b scorer MUST parse lag from claim text as fallback for these records — add `lag_N` tag in signals.py for future buckets, AND add `re.search(r'lag (\d+)', claim)` fallback in scorer for existing records. Fix before 2026-07-09. (f) `cycle.top_up` still fires — non-theater FORMULATED hypotheses remain in pool; if promoted to TESTING they may re-trigger `no_claim_faithful_dataset` skip. Monitor. (g) DELETE stale: `runtime/.handoff/URGENT-atlas-frozen-loop-2026-06-11T20-26Z.md`. (h) CRITICAL PATH: Phase 2b (score predictions → live_observation evidence) must ship before 2026-07-09. Spec in CAUSAL_LOOP_AUDIT.md §2b). Estimated ~2–3h attended session.** **(a) Reflection loop restored — Jun 27 + Jun 28 reflections succeeded; 401 root cause still unknown. (b) No attended sessions; 2 all-continue cycles in window (00:31Z, 01:31Z). (c) Evidence=253 FROZEN (17th+ window). (d) ALL 5 active hypotheses have `symbol=None`; loop does zero epistemic work. (e) consecutive_empty_count=**341**. (f) S3-P2 gate permanently silenced (`emitted_for_current_streak: true`). (g) graph/causal_graph.json **138-LINE** uncommitted drift (~19 days) — `git add graph/causal_graph.json && git commit` before any checkout/reset. (h) DELETE: `URGENT-atlas-unpushed-commits-3rd-cycle.md` stale (push resolved Jun 11; 18 remaining unpushed are reflect-only commits, not code hazard). (i) ACTIVE URGENT: `URGENT-atlas-frozen-loop-2026-06-11T20-26Z.md` — now **~390h** unacknowledged (16+ days); **ROUTING BUG**: runner writes to `runtime/.handoff/`, general session reads `supervisor/handoffs/INBOX/` — these do not overlap. (j) **P2 fix at 22nd carry-forward** — two-part: (1) `runner.py:1362` change `decision=continue` to mark INFEASIBLE + persist when `is_graph_gap and not datasets`; (2) add `if h.symbol is None: return True` to `_claim_is_permanently_infeasible()`. Both changes required to eject active set AND pool. Attended session ~30–45 min. (k) 18 CURRENT_STATE.md-only commits unpushed to origin/main. (l) `signals_found=22` every cycle — signals exist but blocked by dead pool. (m) Synthesis Proposal 4 non-functional for atlas — zero URGENT files in `supervisor/handoffs/INBOX/` after 22+ cycles.**
1. **Test baseline**: 168. Run `.venv/bin/python -m pytest` before any commit.
2. **P3 still deferred** (principal-class): 2 FORMULATED hypotheses reference excluded 4h timeframe — `_claim_is_permanently_infeasible` doesn't catch excluded timeframes. `cycle.top_up skipped_not_promotable: 5` confirms these remain blocked. No action without principal direction.
3. **Migration merge-collapse** (5th carry-forward): `scripts/migrate_claim_hash.py` merge path discards non-claim fields. `--allow-merge` gate aborts on detection but merge-allowed behavior is untested. Add fixture with differing `rationale` fields.
