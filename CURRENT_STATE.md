# CURRENT_STATE — atlas

**Last updated**: 2026-04-19T14-50Z — attended session (claude-opus-4-6)

---

## Deployed / running state
- **Mode**: autonomous research loop (signal intake → hypothesis → experiment → evidence → graph update)
- **Domain**: crypto markets (Bitstamp for deep OHLCV history — Binance/Bybit blocked on Hetzner US server)
- **Entry**: CLI for debugging; `atlas run --interval 3600` for production
- **Data stores**: `methodology.jsonl`, `pending_revalidation.jsonl`, `graph/`, `.atlas/`, `.canon/` (new)

## What just shipped

### Exchange + timeframe fix (uncommitted, 2026-04-19 ~14:50 UTC)
Attended session `c5472d70` (Opus 4.6) fixed the structural blocker that kept all hypotheses stuck at "continue" for 4+ reflection cycles:
- **Root cause**: CLI defaulted to Kraken (`--exchange kraken`), which caps OHLCV at ~720 bars regardless of `since` parameter. `market.py` was designed for Bitstamp's deep pagination (99K+ 1h bars from 2015).
- **Fix**: Changed CLI default exchange to `bitstamp` (aligns with `market.py` design and runner's own default). Removed 4h from DEFAULT_UNIVERSE (1h only: BTC, ETH, SOL). Updated two hardcoded 4h references. Made `_BITSTAMP_SYMBOLS` mapping conditional on exchange.
- **Result**: `atlas run --once` completed with 5 hypotheses tested, 10 experiments, real walk-forward OOS stats. 4 hypotheses found strong contradictions (correctly falsified). 1 hypothesis (weekend volatility) weak/inconclusive → continues.
- **SOL gap**: SOL/USDT on Bitstamp produced no signals during scan (data available but possibly too short for signal detection). Effectively 2 datasets (BTC, ETH), not 3.

### Canon adapter + backfill (commit 1d627c3, 2026-04-19 04:19 UTC)
Workspace executive session `847b6afa` (Opus 4.7) implemented the L1 discovery-framework adapter per ADR-0026 and agentstack plan `calm-squishing-peacock.md`. Components:
- `src/atlas/adapters/discovery/emit.py` (475 LOC) — `emit_claim`, `emit_evidence`, `emit_decision`, `emit_event_log`, `emit_policy_tier_mapping`
- `src/atlas/adapters/discovery/migrate.py` (253 LOC) — one-shot backfill with JSON Schema validation
- `src/atlas/adapters/discovery/MAPPING.md` — documents lossy atlas.quality → canon.tier mapping
- `tests/test_canon_adapter.py` — 16 new tests; total now **97/97**
- `.canon/` backfill: 47 claims, 123 evidence, 82 event_log, 1 policy, **0 decisions**

**Known gap**: `migrate.py` never calls `emit_decision()`. The 40 falsified hypotheses have no Decision records in `.canon/decisions/`. The function exists in `emit.py` but is not called by the migration script.

**Architectural note**: this commit was authored by the executive session, violating the workspace convention (exec sessions should not write project code directly). The adapter is correct and tested; but future refactors should route through an atlas project session.

**This commit is not pushed — branch is 2 ahead of origin/main.**

### Codex adversarial review of 040c053 (commit a55cab0, 2026-04-18 ~22:51 UTC)
Post-hoc review of the canonical claim-hash migration (`040c053`). Review artifact at `.reviews/040c053-review-2026-04-18T22-51-16Z.md`. Three findings (see Open Items). Also not pushed.

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
- **Merge-on-canonical assumption** — `scripts/migrate_claim_hash.py` lines 146–170 auto-merges hypotheses that hash to the same canonical form. Apr 18 run produced zero merges, but behavior persists. No test covers merge scenario.
- **Non-transactional migration** — script deletes hypothesis files (Phase 3) before finishing downstream re-links (Phases 4–5). Crash leaves mixed-ID state with no recovery path.
- **Evidence ID leakage** — post-migration re-ingest of old findings produces new `ev_id`s. Cosmetic but accumulates indefinitely.

### Structural blockers
- **`/review` EROFS** — `/review` skill still blocked. Three significant changes (`c5b7a13`, `040c053`, `1d627c3`) have now shipped without pre-review. INBOX proposal `proposal-tick-prompt-adversarial-review-gate-2026-04-17T22-48Z.md` awaits attended session decision.
- ~~**4h data too short for walk-forward**~~ **RESOLVED** — Root cause was CLI defaulting to Kraken (720-bar cap), not just the timeframe. Fixed: default exchange → bitstamp (99K+ 1h bars), DEFAULT_UNIVERSE → 1h only. Validated with `atlas run --once`: 10 experiments completed with proper stats.
- **Branch not clean** — two commits (`a55cab0`, `1d627c3`) not pushed to origin/main. `CURRENT_STATE.md` dirty.

### Telemetry / methodology gaps
- **`evidence_count` telemetry misleading** — `runner.py:915` emits total store size. 3rd cycle unaddressed.
- **methodology.jsonl feedback loop structurally absent** — signal-source quality untracked.
- **`created_at` non-determinism in concurrent evidence writes**: cosmetic only.
- **Backtest ≠ live performance**: known limitation, Phase 2.

## Blocked on
- `/review` EROFS is a system issue for the general session to resolve.

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
1. Run `.venv/bin/python -m pytest` to confirm **97/97** baseline (was 81; +16 canon adapter tests).
2. Push all unpushed commits (`git push`) to restore remote consistency.
3. ~~**URGENT**: Switch runner timeframe~~ **DONE** — Exchange + timeframe fix applied and validated.
4. Fix `migrate.py` to emit Decision records for falsified hypotheses — call `emit_decision()` for each `status in (FALSIFIED, SUPPORTED, PROMOTED)`. Function is at `emit.py:265`.
5. Read `.reviews/040c053-review-2026-04-18T22-51-16Z.md` — merge-on-canonical and crash-safety gap still unaddressed.
6. Fix `runner.py:915` `evidence_count` field. Then invoke `/review` on the canon adapter (significant new code, no adversarial review yet).
7. **SOL dataset gap**: SOL/USDT on Bitstamp produced no signals. Investigate whether SOL/USD 1h data is too short or signal detectors don't match. Only 2 datasets (BTC, ETH) used for cross-validation.
