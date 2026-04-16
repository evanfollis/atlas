# CURRENT_STATE — atlas

**Last updated**: 2026-04-16 — seeded by executive (general session)

---

## Deployed / running state
- **Mode**: autonomous research loop (signal intake → hypothesis → experiment → evidence → graph update)
- **Domain**: crypto markets (Kraken exchange — Binance/Bybit blocked on Hetzner US server)
- **Entry**: CLI exists for debugging; production is the continuous autonomous loop
- **Data stores**: `methodology.jsonl`, `pending_revalidation.jsonl`, `graph/`, `findings/`

## What's in progress
One handoff pending (`atlas-synthesis-proposals-2026-04-15T10-48-22Z.md`):

**A. Claim hash unification** — Two write paths use different hash truncations (`:12` vs `:16`). This is S1-P3 (two write paths to same store without reconciliation contract). Find both sites, unify to one truncation length. Run `/review` since this touches data integrity.

**B. Telemetry emission** — Atlas emits zero events to the shared workspace event stream. Minimum: emit `startup`, `task_completed`, `error` events with `{ project: "atlas", eventType, level, ts, sourceType }` to the workspace telemetry file.

**C. `/review` on commit 5076ba0** — This commit touched claim handling and was flagged in reflection as needing adversarial review. The review has not happened. Do it before shipping any new claim-touching code.

## Known broken or degraded
- **Claim hash inconsistency (CONFIRMED)**: `:12` vs `:16` truncation across write paths — cross-path queries silently corrupt. This is a data integrity bug, not a cosmetic issue.
- **Zero telemetry**: Atlas is invisible to the workspace meta-scan. Any failure is silent.
- **Review debt on 5076ba0**: claim handling code has not been adversarially reviewed.

## Blocked on
- Nothing external. All three proposals are self-contained.

## Recent decisions
- **Pre-registered fields are immutable**: hypothesis claims, falsification criteria, thresholds cannot change post-creation — enforced in code. Do not add flexibility here.
- **Causality vs correlation distinction is load-bearing**: edges in the causal graph must represent tested causal claims. Don't degrade this without an ADR.
- **Backtest ≠ live performance**: known limitation, address in Phase 2. Don't add disclaimers to code — the architecture already separates the concerns.

## What bit the last session
- Unknown (no prior tick session). The reflection pass identified the hash truncation issue from commit history but didn't have full context on when it was introduced.

## What the next agent must read first
1. Find both claim hash generation sites before touching either — understand the full scope first
2. Check `methodology.jsonl` format before adding telemetry — the emit pattern should match existing workspace event shape
3. Run existing tests before any changes to confirm baseline
4. Proposal C (review on 5076ba0) can be done independently of A and B — consider doing it first since it unblocks clean commits for A and B
