# CURRENT_STATE — atlas

**Last updated**: 2026-04-18T02-26-40Z — reflection pass (claude-sonnet-4-6)

---

## Deployed / running state
- **Mode**: autonomous research loop (signal intake → hypothesis → experiment → evidence → graph update)
- **Domain**: crypto markets (Kraken/Bitstamp — Binance/Bybit blocked on Hetzner US server)
- **Entry**: CLI for debugging; `atlas run --interval 3600` for production
- **Data stores**: `methodology.jsonl`, `pending_revalidation.jsonl`, `graph/`, `.atlas/`

## What just shipped

### Housekeeping (commits 805f264 + 0faa536, 2026-04-17 19:23–19:24 UTC)
Both commits were attended-session work (Opus 4.6), directly actioning prior-reflection proposals.

- **805f264** — Closed stale telemetry-field carry-forward: workspace CLAUDE.md spec reconciled to `timestamp` (epoch ms integer). No atlas code change needed. Recorded as settled decision.
- **0faa536** — Moved 15-line "Identity and concurrency properties" docstring out of `ingest.py` into CLAUDE.md §Key Design Decisions. Style policy compliance restored.

**Branch status**: 2 commits ahead of origin/main (not pushed).

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

- **`/review` EROFS** — `/review` skill still blocked. INBOX has a proposal to wire `adversarial-review.sh` into the tick prompt as a gate (`proposal-tick-prompt-adversarial-review-gate-2026-04-17T22-48Z.md`). General session must decide.
- **Live end-to-end path unvalidated (URGENT — 3rd cycle escalation)**: No `atlas run --once` has run since the claim-hash migration (3+ ticks). Zero telemetry events emitted under current ev_id schema. Methodology feedback loop has no real signal. URGENT handoff filed: `URGENT-atlas-live-path-unvalidated.md`. If blocked on credentials, record the blocker explicitly.
- **`created_at` non-determinism in concurrent evidence writes**: with atomic writes, two concurrent workers produce logically equivalent evidence records with different `created_at` values; last-write-wins. Cosmetic only — the ID and all substantive fields are identical.
- **Backtest ≠ live performance**: known limitation, Phase 2.

## Blocked on
- Nothing urgent. `/review` EROFS is a system issue for the general session to resolve.

## Known gotchas
- `.venv/bin/pytest` shebang points to old path. Use `.venv/bin/python -m pytest`.
- `list_all()` in StateStore now skips `.tmp` files (suffix check added) — safe to have tmp files in state dirs during concurrent writes.
- The migration script (`scripts/migrate_claim_hash.py`) is idempotent — safe to re-run. Current version handles the canonical-form migration (schema v2).
- Ingest-created evidence IDs embed `hyp_id` in their hash. Post-migration, re-ingesting old findings would compute a different ev_id (new canonical hyp_id). This is cosmetic — the old evidence record persists; re-ingest creates a new record alongside it.
- Evidence `source_hash` is empty string `""` on records created before c5b7a13 (runner-generated evidence). Only ingest-pipeline evidence has it set. That's correct — the field is optional.
- `methodology.jsonl` has 3 pre-attribution records (no `generation_method`); methodology feedback loop will run on neutral weights until new records accumulate.

## Recent decisions
- **Claim hash canonical: [:16] of SHA-256 with strip()**. `utils.py` is the single source of truth.
- **Evidence ID is now deterministic**: `sha256(hyp_id:exp_id:block_content_hash)[:16]`. Two writers, same input → same ID → safe.
- **StateStore writes are atomic**: tmpfile + os.replace. No explicit file locks.
- **Revalidation queue is append-only**: dedup-on-read, not dedup-on-write.
- **Pre-registered fields are immutable**: enforced in StateStore. Do not relax.
- **Causality vs correlation distinction is load-bearing**: edges must represent tested causal claims.
- **Telemetry field name reconciled (2026-04-17)**: atlas `runner.py::_emit_telemetry` emits `timestamp` (epoch ms integer). Workspace CLAUDE.md spec reconciled to match — no atlas code change needed.
- **Claim-hash canonical migration (2026-04-18)**: Principal decided MIGRATE (not reset). `claim_canonical()` added to `utils.py` (lower + ws-collapse + strip trailing punct). All 42 hypotheses re-keyed, 123 experiments + 123 evidence re-linked, zero merges, zero orphans. Schema version bumped to 2. Known artifact: ingest-created evidence IDs embed old `hyp_id` — a re-ingest of old findings would generate a new ev_id rather than deduplicating against the migrated record.

## What the next agent must read first
1. Run `.venv/bin/python -m pytest` to confirm 81/81 baseline.
2. Run `atlas run --once` to validate the live exchange path (overdue since claim-hash migration).
3. Next highest-leverage items: push to origin/main, on-chain/funding-rate signal detectors.
