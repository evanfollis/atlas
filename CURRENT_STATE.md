---
name: CURRENT_STATE
description: Front door for atlas — live research-loop state, canon gap closure status, deployment mode
type: front-door
updated: 2026-04-25
---

# CURRENT_STATE — atlas

**Last updated**: 2026-04-25T16:00Z — frozen-loop fix DEPLOYED + verified (cycle.completed shows {kill:5}, evidence 133→143); --allow-merge gate landed; deploy-push gate landed

---

## Deployed / running state
- **Mode**: autonomous research loop (signal intake → hypothesis → experiment → evidence → graph update). **RUNNING** as of 2026-04-24T12:27Z under `systemctl status atlas-runner.service`. Frozen-loop fix bf6fc4e deployed at 2026-04-25T15:45:12Z. First post-restart cycle.completed shows `{decisions_by_kind: {kill: 5}, total_evidence_store_size: 143}` — all 5 hypotheses correctly falsified with fresh evidence (was previously `{continue: 5}` frozen at 133). The freshness cache (`DATASET_RETEST_AFTER = 1 day`) is doing exactly what it should.
- **Domain**: crypto markets (Bitstamp for deep OHLCV history — Binance/Bybit blocked on Hetzner US server).
- **Entry**: production = `systemctl status/start/stop atlas-runner.service`. Debug = `.venv/bin/atlas run --once` from project root.
- **Service unit**: `/etc/systemd/system/atlas-runner.service`; mirrored copy in repo at `deploy/atlas-runner.service` for re-installation. Re-install with `sudo install -m644 deploy/atlas-runner.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now atlas-runner.service`.
- **Data stores**: `methodology.jsonl`, `pending_revalidation.jsonl`, `graph/`, `.atlas/`, `.canon/`.

## What just shipped
- **Frozen-loop fix deployed + verified (2026-04-25T15:58Z)**: bf6fc4e pushed and `atlas-runner.service` restarted at 15:45:12Z. First post-restart cycle.completed: `{decisions_by_kind: {kill: 5}, total_evidence_store_size: 143, signals_found: 22}`. Five hypotheses correctly falsified with fresh evidence (was 5 × continue, evidence frozen at 133).
- **`--allow-merge` gate on `migrate_claim_hash.py` (commit 4977ad9)**: per `URGENT-atlas-migration-merge-collapse`. Merge groups now abort the migration with `SystemExit(2)` and a per-field divergence audit. Audit of current `.atlas/hypotheses/`: 59 records, 0 with `claim_variants` populated → no prior runs ever silently merged anything. Tests: 109 → 111.
- **Deploy-push gate (commit 0fedaf2)**: `deploy/README.md` documents the rule (push+restart OR `code_landed_NOT_deployed` note in CURRENT_STATE.md). `scripts/deploy-check.sh` is a non-blocking diagnostic for unpushed-commits + service-vs-commit-time skew.
- **`cycle.completed` telemetry (2026-04-24T15:37Z, commit 66a3db7)**: `runner.py` emits `cycle.completed` on the happy path with `decisions_by_kind`, `signals_found`, `graph_nodes`, `graph_edges`, `total_evidence_store_size`. First post-deploy emission confirmed all-continue frozen-loop state is now directly visible in telemetry.

## Known broken or degraded

- ~~**Evidence accumulation frozen at 133**~~ — **Resolved 2026-04-25T15:58Z**: bf6fc4e pushed and service restarted. Post-restart cycle.completed shows `{kill: 5}` with `total_evidence_store_size: 143`. The freshness fix is live and producing correct falsifications.
- ~~**No `cycle.completed` event**~~ — **Fixed 2026-04-24T15:37Z (commit 66a3db7)**: `runner.py` now emits `cycle.completed` on the happy path with `decisions_by_kind` payload. First post-deploy emission confirmed `{"continue": 5}` across 5 hypotheses with `total_evidence_store_size=133` — the all-continue frozen-loop state is now directly visible in telemetry. (`cycle.failed` already existed at line 975.)
- **`/review` EROFS** still blocks; workaround via `adversarial-review.sh` in use.

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
1. **Deploy the retest-window patch**: commit `bf6fc4e` is NOT pushed and the service is NOT restarted. Run: `git push origin main && sudo systemctl restart atlas-runner.service`. Then verify the next cycle shows new `run_experiment` calls in the journal (not just "skipping already tested"). All 133 evidence records are from 2026-04-19 — the patch will immediately unblock retesting once live.
2. **Add S3-P2 all-continue escalation**: after N (=3) consecutive `cycle.completed` events all showing `decisions_by_kind == {"continue": n}`, emit an `escalated` event and write a handoff to `runtime/.handoff/URGENT-atlas-frozen-loop-<ts>.md`. The loop is now 6+ cycles in without this self-reporting. See P3.
3. Run `.venv/bin/python -m pytest` to confirm **107/107** baseline.
4. Address the 2026-04-23 merge-destructive finding: `scripts/migrate_claim_hash.py` silently collapses non-claim fields on hypotheses that share a canonical hash. Add an explicit `--allow-merge` gate and a merge-group test fixture. See `supervisor/.reviews/atlas-migration-reorder-2026-04-23T17-13Z.md`.
5. If dual-write or canon-intake is next: rewire adapter callers to pass real `sources=` instead of default `[]`, and design a transaction for the `.atlas ↔ .canon` dual-write boundary.
