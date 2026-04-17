# CURRENT_STATE — atlas

**Last updated**: 2026-04-17 — tick session (claude-sonnet-4-6)

---

## Deployed / running state
- **Mode**: autonomous research loop (signal intake → hypothesis → experiment → evidence → graph update)
- **Domain**: crypto markets (Kraken/Bitstamp — Binance/Bybit blocked on Hetzner US server)
- **Entry**: CLI for debugging; `atlas run --interval 3600` for production
- **Data stores**: `methodology.jsonl`, `pending_revalidation.jsonl`, `graph/`, `.atlas/`

## What just shipped (commit c1395bb)
- **Claim hash unified to [:16]**: `src/atlas/utils.py` is the canonical source; both `runner.py` and `ingest.py` import from it. State store migrated: 40 hypotheses, 120 evidence, 120 experiment records — zero collisions. All tests pass (75/75).
- **Evidence deduplication**: `ingest_finding()` skips re-writing evidence when `(hypothesis_id, experiment_id)` already exists; same guard on revalidation queue append.
- **Workspace telemetry live**: `_emit_telemetry()` in runner emits `cycle.started`, `hypothesis.decided`, and `cycle.failed` events to `/opt/workspace/runtime/.telemetry/events.jsonl`. Atlas is now visible to meta-scan.
- **Methodology feedback loop closed**: `generate_hypotheses()` tracks `(hypothesis, source_method)` through the full pipeline, logs `hypothesis_sources` records to `methodology.jsonl`, and uses `compute_method_weights()` (Laplace-smoothed promotion rate) to break prioritization ties. Neutral until evidence accumulates.

## Open items
- **`/review` on ingest.py (commit 5076ba0) NOT done**: `/review` skill failed with `EROFS: read-only file system, open '/root/.claude.json'`. This is a system-level blocker, not a code issue. Escalated to executive. The specific review targets are: concurrent writers with no locking, evidence dedup correctness, revalidation queue unbounded append.
- **File locking still deferred**: StateStore has no write locking. Single-process assumption holds for now; concurrent access remains a known gap (Review #3/#4 finding).
- **Backtest ≠ live performance**: known limitation, Phase 2.

## Blocked on
- `/review` blocked by `EROFS` on `/root/.claude.json` — system issue, not code. Executive must resolve before adversarial review can run.

## Known gotchas
- The `.venv/bin/pytest` shebang points to `/opt/projects/atlas/.venv/bin/python3` (old path). Use `.venv/bin/python -m pytest` instead.
- Existing `methodology.jsonl` records predate `hypothesis_sources` phase — weights start neutral (0.5) and learn forward. That's correct behavior.
- The migration script (`scripts/migrate_claim_hash.py`) is idempotent — safe to re-run, skips already-[:16] files.

## Recent decisions
- **Claim hash canonical: [:16] of SHA-256 with strip()**. `utils.py` is the single source of truth. Never inline another hash function.
- **Pre-registered fields are immutable**: hypothesis claims, falsification criteria, thresholds — enforced in StateStore. Do not add flexibility here.
- **Causality vs correlation distinction is load-bearing**: edges must represent tested causal claims.
- **Backtest ≠ live performance**: known limitation, Phase 2.

## What the next agent must read first
1. Check `/opt/workspace/runtime/.handoff/` for the `/review` escalation before anything else — it needs a human or system fix.
2. Methodology feedback loop is live but has no data yet. First few autonomous cycles will produce `hypothesis_sources` records; subsequent cycles will have real weights.
3. Run `.venv/bin/python -m pytest` not `.venv/bin/pytest` (shebang is stale).
4. Next highest-leverage items (from executive handoff): on-chain/funding-rate signal detectors, Granger causality for causal edge justification.
