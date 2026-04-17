# CURRENT_STATE — atlas

**Last updated**: 2026-04-17T14-23-10Z — reflection pass (claude-sonnet-4-6)

---

## Deployed / running state
- **Mode**: autonomous research loop (signal intake → hypothesis → experiment → evidence → graph update)
- **Domain**: crypto markets (Kraken/Bitstamp — Binance/Bybit blocked on Hetzner US server)
- **Entry**: CLI for debugging; `atlas run --interval 3600` for production
- **Data stores**: `methodology.jsonl`, `pending_revalidation.jsonl`, `graph/`, `.atlas/`

## What just shipped

### Codex adversarial review fixes (commit c5b7a13, 2026-04-17 09:19 UTC)
Three findings from the Codex review of `ingest.py` (review blocked for 5 cycles, landed via codex-exec path).

**Finding 2 — Deterministic evidence ID** (`src/atlas/research/ingest.py`, `src/atlas/models/evidence.py`)
- Evidence ID is now `sha256(hyp_id:exp_id:block_content_hash)[:16]` — deterministic from file content.
- Two concurrent workers ingesting the same file compute the same ev_id (last-write-wins is benign, same logical content).
- Dedup check changed from O(n) `list_all()` scan to O(1) `store.load("evidence", ev_id)`.

**Finding 2 — Atomic writes in StateStore** (`src/atlas/storage/state_store.py`)
- `save()` now writes to a tmpfile then renames (`os.replace`) — atomic on Linux.
- Readers never observe a partial write. Concurrent writers are safe: both succeed, last-write-wins for new objects.

**Finding 3 — Content snapshot** (`src/atlas/research/ingest.py`, `src/atlas/models/evidence.py`)
- `block_content_hash`: `sha256[:16]` of the raw YAML text inside the `<!-- atlas-finding ... -->` block, captured at ingest time.
- Stored as `source_hash` on the Evidence record and `block_content_hash` in Experiment.parameters.
- A post-ingest edit to the finding block produces a different evidence ID on re-ingest — mutation surfaces as a new record rather than silently overwriting.

**Finding 2 — Revalidation queue: append-only + dedup-on-read**
- Removed pre-write dedup check (race-prone read-then-act). Queue is now always append-only.
- `due_revalidations()` deduplicates by experiment_id at read time (`seen` set), so concurrent or repeated appends don't produce duplicate scheduled re-runs.

**Test baseline**: 81/81 (was 75/75, 6 new tests cover deterministic ID, content hash, real concurrent threading, revalidation dedup).

### Previously shipped (commit c1395bb)
- Claim hash unified to [:16], evidence dedup, workspace telemetry, methodology feedback loop.

## Open items
- **`/review` EROFS** — `/review` skill still blocked. Check `/opt/workspace/runtime/.handoff/` for resolution status. Note: this tick's changes were reviewed via Codex-exec path (adversarial review landed). The EROFS blocks the interactive `/review` skill only.
- **Finding 1 — claim_hash as canonical identity (documented, not fixed)**:
  - Raw claim text (strip()-only) is the key. Wording drift forks the same hypothesis; semantic duplicates silently merge.
  - Fix requires: canonicalize before hashing (lowercase + whitespace-normalize + strip punctuation) + one-shot migration that re-keys all `.atlas/hypotheses/*.json` files. This is ADR-class — do not do it inline.
  - Draft plan: (a) add `claim_canonical()` to `utils.py` that applies full normalization, (b) write a migration script similar to `scripts/migrate_claim_hash.py` that loads each hypothesis, re-hashes with the new function, renames the file, re-links experiments and evidence. (c) bump schema version.
  - Decision needed: whether to migrate 40 existing hypotheses or reset (research is early-stage). Migration script is ready either way.
- **Live end-to-end path unvalidated**: No `atlas run --once` has run since the claim-hash migration (2+ ticks). Run this before shipping next feature.
- **`created_at` non-determinism in concurrent evidence writes**: with atomic writes, two concurrent workers produce logically equivalent evidence records with different `created_at` values; last-write-wins. Cosmetic only — the ID and all substantive fields are identical.
- **Backtest ≠ live performance**: known limitation, Phase 2.

## Blocked on
- Nothing urgent. `/review` EROFS is a system issue for the general session to resolve.

## Known gotchas
- `.venv/bin/pytest` shebang points to old path. Use `.venv/bin/python -m pytest`.
- `list_all()` in StateStore now skips `.tmp` files (suffix check added) — safe to have tmp files in state dirs during concurrent writes.
- The migration script (`scripts/migrate_claim_hash.py`) is idempotent — safe to re-run.
- Evidence `source_hash` is empty string `""` on records created before this tick (runner-generated evidence). Only ingest-pipeline evidence has it set. That's correct — the field is optional.
- `methodology.jsonl` has 3 pre-attribution records (no `generation_method`); methodology feedback loop will run on neutral weights until new records accumulate.

## Recent decisions
- **Claim hash canonical: [:16] of SHA-256 with strip()**. `utils.py` is the single source of truth.
- **Evidence ID is now deterministic**: `sha256(hyp_id:exp_id:block_content_hash)[:16]`. Two writers, same input → same ID → safe.
- **StateStore writes are atomic**: tmpfile + os.replace. No explicit file locks.
- **Revalidation queue is append-only**: dedup-on-read, not dedup-on-write.
- **Pre-registered fields are immutable**: enforced in StateStore. Do not relax.
- **Causality vs correlation distinction is load-bearing**: edges must represent tested causal claims.
- **Telemetry field name reconciled (2026-04-17)**: atlas `runner.py::_emit_telemetry` emits `timestamp` (epoch ms integer). Workspace CLAUDE.md spec was reconciled to match on 2026-04-17 — no atlas code change needed.

## What the next agent must read first
1. Run `.venv/bin/python -m pytest` to confirm 81/81 baseline.
2. Run `atlas run --once` to validate the live exchange path (still unexercised since c1395bb migration — 2+ ticks overdue).
3. Finding 1 (claim_hash canonical identity) is **documented but not fixed**. Read the Open Items section above for the concrete migration plan before touching claim hashing.
4. Next highest-leverage items: run live path, claim-hash migration decision, on-chain/funding-rate signal detectors.
