---
name: CURRENT_STATE
description: Front door for atlas — live research-loop state, canon gap closure status, deployment mode
type: front-door
updated: 2026-06-10T14-20-00Z
---

# CURRENT_STATE — atlas

**Last updated**: 2026-06-10T14:20Z — reflection pass (12h). **3 commits NOT pushed to origin/main** (b0df455, 8249acc, c6d7288) — push is now 2 consecutive reflections overdue; next cycle triggers URGENT escalation per carry-forward rule. Evidence frozen at 244 across 12+ consecutive cycles since ADR-0035 deploy. Loop structurally idle: decisions={continue:5} every cycle, graph_nodes=69/graph_edges=0 unchanged. Two graph-gap hypotheses skip with `no_claim_faithful_dataset` every cycle; three others evaluate without advancing evidence (sub-case undiagnosed — freshness gate or zero-signal).

**Previous (2026-06-10T02:18Z)**: ADR-0035 deployed; evidence frozen at 244; 2 commits not pushed. Graph-gap hypotheses generate but skip with `no_claim_faithful_dataset`. Prior claim that manual validation "created evidence" was unverified by telemetry.

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
- **Test count** — 168 after 71224e9 (P1 +12). Verified: `.venv/bin/python -m pytest` → `168 passed`.
- ~~**State file timestamp anomaly**~~ — **Resolved 2026-04-27T17:00Z**: my original seed had a 14-hour math error (used 07:30Z when I claimed 21:30Z). Re-seeded with verified values from the 04-27 02:36:44Z emission visible in current events.jsonl: `{"last_streak_start_ts": 1777250052457, "last_emitted_ts": 1777257404561}`. Gate is now correctly anchored.
- **Concurrent runner safety** (known soft edge, not URGENT): `_maybe_escalate_frozen_loop` read-check-write is not atomic. A parallel `atlas run --once` debug session running alongside the live service could double-emit. Worst case is 2 telemetry events + 1 URGENT file (handoff dedup wins eventually). flock would close it; tracked but deferred per the 17:00Z review.
- **Cache-vs-gate misalignment** (open, principal-class): `DATASET_RETEST_AFTER = 1 day` and `FROZEN_LOOP_ESCALATION_AFTER = 3 cycles` interact such that the gate fires roughly once per 24h between productive cycles. The gate firing is correct epistemic signal (the loop genuinely cannot promote during the cache window), but produces a recurring URGENT. Tuning options A–D documented in `general-atlas-frozen-loop-diagnosis-2026-04-25T21-40Z.md`. No code change without principal direction. Confirmed cadence via 04-26 18:14Z kill (evidence 153→163) → 21:30Z escalation (3-cycle new streak); the dedup-fixed gate is working precisely as documented.
- **Telemetry pollution (cosmetic)**: 4 `cycle.escalated` events in `events.jsonl` from initial test runs before `_emit_telemetry` was refactored to honor `self.TELEMETRY_PATH`. Bogus markers (`streak_start_ts=1000`, `evidence=0`); harmless to gate logic. Not scrubbing the shared file.
- ~~**Evidence accumulation frozen at 133**~~ — **Resolved 2026-04-25T15:58Z**: bf6fc4e pushed and service restarted. Post-restart cycle.completed shows `{kill: 5}` with `total_evidence_store_size: 143`. The freshness fix is live and producing correct falsifications.
- ~~**No `cycle.completed` event**~~ — **Fixed 2026-04-24T15:37Z (commit 66a3db7)**: `runner.py` now emits `cycle.completed` on the happy path with `decisions_by_kind` payload. First post-deploy emission confirmed `{"continue": 5}` across 5 hypotheses with `total_evidence_store_size=133` — the all-continue frozen-loop state is now directly visible in telemetry. (`cycle.failed` already existed at line 975.)
- **THREE COMMITS NOT PUSHED (P1, 2nd consecutive reflection)**: `b0df455`, `8249acc`, and `c6d7288` (reflection CURRENT_STATE update) are deployed/local but NOT in `origin/main`. `git push origin main` needed immediately — next reflection cycle triggers URGENT escalation per workspace carry-forward rule. Any `git reset --hard origin/main` would revert running code to pre-ADR-0035.
- **Evidence frozen at 244**: Graph-gap hypotheses generate each cycle but skip with `no_claim_faithful_dataset`. The 2 skipped hypotheses are saved to `.atlas/hypotheses/` as FORMULATED and re-evaluated every cycle. Evidence store has not grown since before ADR-0035 deploy. Research loop runs but produces no new results.
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
0. **LOOP STATE: RUNNING + EVIDENCE FROZEN — updated 2026-06-10T14:20Z (reflection)**. ADR-0035 shipped (69 refuted graph nodes); loop now evaluates 5 hypotheses/cycle (was 0). **All 5 produce {continue} every cycle — zero evidence generated since deploy.** **(a) 3 commits not pushed to origin/main (b0df455, 8249acc, c6d7288) — push immediately; next reflection triggers URGENT escalation. (b) evidence frozen at 244 across 12+ cycles. (c) 2 graph-gap hypotheses skip every cycle with no_claim_faithful_dataset; 3 others evaluate but produce no evidence — sub-cause undiagnosed (freshness gate? zero signal?). (d) S3-P2 escalation gate permanently blind (emitted_for_current_streak: true) — resets only on decisive cycle which deadlock prevents.** Next leverage point per prior reflection: fix hypothesis persistence order (P2), diagnose 3 non-skipping hypotheses (P3), or pursue ADR-class forward-prediction ledger / feature-space expansion (principal decision needed). See CAUSAL_LOOP_AUDIT.md for causal chain.
1. **Test baseline**: 168. Run `.venv/bin/python -m pytest` before any commit.
2. **P3 still deferred** (principal-class): 2 FORMULATED hypotheses reference excluded 4h timeframe — `_claim_is_permanently_infeasible` doesn't catch excluded timeframes. `cycle.top_up skipped_not_promotable: 5` confirms these remain blocked. No action without principal direction.
3. **Migration merge-collapse** (5th carry-forward): `scripts/migrate_claim_hash.py` merge path discards non-claim fields. `--allow-merge` gate aborts on detection but merge-allowed behavior is untested. Add fixture with differing `rationale` fields.
