# CURRENT_STATE — atlas

**Last updated**: 2026-04-20T17-00Z — URGENT carry-forward handoff resolved (telemetry rename + canon-adapter adversarial review)

---

## Deployed / running state
- **Mode**: autonomous research loop (signal intake → hypothesis → experiment → evidence → graph update)
- **Domain**: crypto markets (Bitstamp for deep OHLCV history — Binance/Bybit blocked on Hetzner US server)
- **Entry**: CLI for debugging; `atlas run --interval 3600` for production
- **Data stores**: `methodology.jsonl`, `pending_revalidation.jsonl`, `graph/`, `.atlas/`, `.canon/` (new)

## What just shipped

### URGENT carry-forward resolution (2026-04-20T17Z) — UNCOMMITTED
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
- **No Decision records backfilled** — `migrate.py` does not call `emit_decision()`. 40 falsified hypotheses have no canon Decision records. `emit_decision()` in `emit.py` line 265 is ready; the migrate.py loop is missing.

### Unresolved Codex findings (from a55cab0 review of 040c053)
- **Non-transactional migration** — script deletes hypothesis files (Phase 3) before finishing downstream re-links (Phases 4–5). Crash leaves mixed-ID state with no recovery path. **Highest severity** — data-loss path.
- **Merge-on-canonical assumption** — `scripts/migrate_claim_hash.py` lines 146–170 auto-merges hypotheses that hash to the same canonical form. Apr 18 run produced zero merges, but behavior persists. No test covers merge scenario.
- **Evidence ID leakage** — post-migration re-ingest of old findings produces new `ev_id`s. Cosmetic but accumulates indefinitely.

### Unresolved Codex findings (from 2026-04-20 review of canon adapter 1d627c3)
- **`sources=[]` hardcoded** (emit.py:146–160) — adapter assumes atlas never cites upstream canon. If atlas starts ingesting canon records, every emitted envelope will falsely claim first-party provenance. Blast radius: lineage/trust/dedupe across `.canon/`. **Mitigation needed before dual-write or canon-ingestion lands.**
- **No dual-write transaction** — emit_claim depends on `.atlas/hypotheses/<id>.json` existing to attach required artifacts (emit.py:193–202); StateStore.save only guarantees atomicity for the `.atlas` write. Currently moot (one-shot migration), but will bite when dual-write is added.
- **Adapter boundary already eroded** — `canon_dir()` creates directories (emit.py:48–54), emitters read/hash on-disk atlas files (emit.py:66–71, 193–199, 235–240), and migrate.py reaches into private helpers (migrate.py:31–37). Not a "pure projection layer" as docstring claims.

### Structural blockers
- **`/review` EROFS** — `/review` Claude skill still blocked by read-only mount on `/root/.claude.json`. Workaround `supervisor/scripts/lib/adversarial-review.sh` (codex-based) validated in this session. INBOX proposal `proposal-tick-prompt-adversarial-review-gate-2026-04-17T22-48Z.md` awaits attended session decision.

### Telemetry / methodology gaps
- ~~**`evidence_count` telemetry misleading**~~ — **Fixed 2026-04-20**: renamed to `total_evidence_store_size` at `runner.py:914`. Field name now matches behavior.
- **methodology.jsonl feedback loop structurally absent** — signal-source quality untracked.
- **`created_at` non-determinism in concurrent evidence writes**: cosmetic only.
- **Backtest ≠ live performance**: known limitation, Phase 2.

### SOL dataset gap
- **SOL/USDT produces no signals** — Bitstamp SOL/USD data may be too short for signal detectors (signal warmups require 20–50+ bars; SOL has ~3 years vs BTC/ETH's 6+). Only 2 datasets effectively used for cross-validation despite DEFAULT_UNIVERSE listing 3.

## Blocked on
- `/review` EROFS is a system issue for the general session to resolve (INBOX proposal pending decision).

## Known gotchas
- `.venv/bin/pytest` shebang points to old path. Use `.venv/bin/python -m pytest`.
- `list_all()` in StateStore skips `.tmp` files — safe to have tmp files during concurrent writes.
- The migration script (`scripts/migrate_claim_hash.py`) is idempotent for no-merge runs only. Guard with `--allow-merge` flag if merge groups appear.
- Ingest-created evidence IDs embed `hyp_id` in their hash. Post-migration re-ingest produces a new ev_id — cosmetic, old record persists.
- Evidence `source_hash` is `""` on records created before c5b7a13 — correct, field is optional.
- **Canon adapter note**: `.canon/decisions/` is empty. Not a bug in `emit.py` — `emit_decision()` exists and is correct. Gap is in `migrate.py` (never called). If a downstream canon consumer expects Decision records for falsified hypotheses, the backfill must be re-run after fixing migrate.py.

## Recent decisions
- **ADR-0026 (2026-04-19)**: agentstack chartered as third canon instance; atlas adapter shipped as first reference implementation. Adapter-first, L2 runtime extraction deferred.
- **Claim hash canonical: [:16] of SHA-256 with lowercase + ws-collapse + strip trailing punct**. `claim_canonical()` in `utils.py`. Schema v2.
- **Evidence ID is deterministic**: `sha256(hyp_id:exp_id:block_content_hash)[:16]`.
- **StateStore writes are atomic**: tmpfile + os.replace. No explicit file locks.
- **Revalidation queue is append-only**: dedup-on-read, not dedup-on-write.
- **Pre-registered fields are immutable**: enforced in StateStore. Do not relax.
- **Live path validated (2026-04-19)**: `atlas run --once` with Bitstamp 1h data completed. 5 hypotheses tested, 10 experiments with walk-forward OOS stats. 4 found strong contradictions, 1 weak/inconclusive. System produces real falsification decisions.
- **Default exchange is Bitstamp (2026-04-19)**: Kraken caps OHLCV at ~720 bars regardless of `since` — below the 833-bar walk-forward minimum. Bitstamp provides 99K+ 1h bars via pagination.

## What the next agent must read first
1. Run `.venv/bin/python -m pytest` to confirm **97/97** baseline.
2. ~~Push all unpushed commits~~ **DONE** — branch is clean and up to date with origin/main as of 2026-04-20T02:20Z.
3. Fix `migrate.py` to emit Decision records for falsified hypotheses — call `emit_decision()` for each `status in (FALSIFIED, SUPPORTED, PROMOTED)`. Function is at `emit.py:265`.
4. Read `.reviews/040c053-review-2026-04-18T22-51-16Z.md` — non-transactional migration (data-loss path) and merge-on-canonical gap still unaddressed.
5. ~~Fix `runner.py:915` `evidence_count` field~~ **DONE** (renamed to `total_evidence_store_size`). ~~Invoke `/review` on the canon adapter~~ **DONE** via `supervisor/scripts/lib/adversarial-review.sh` — findings logged above under "Unresolved Codex findings".
6. **SOL dataset gap**: SOL/USDT on Bitstamp produced no signals. Investigate whether SOL/USD 1h data is too short or signal detectors don't match. Only 2 datasets (BTC, ETH) used for cross-validation.
