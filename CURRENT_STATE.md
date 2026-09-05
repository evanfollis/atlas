---
name: CURRENT_STATE
description: Bounded operational and scientific snapshot for Atlas
type: front-door
updated: 2026-09-05T04:14:32Z
---

# CURRENT_STATE — Atlas

## Disposition

**PARKED INTENTIONALLY.** `atlas-runner.service` is disabled and inactive. Do
not restart or re-enable it yet. The software gate is green and a new SOL data
supply is technically viable, but two scientific-identity gates below remain
open. Hourly execution of the old loop is not useful work.

No live trading or capital execution exists or is authorized.

## Verified runtime snapshot

Measured from `/opt/workspace/runtime/projects/atlas/` and the repository on
2026-09-05:

- Strategy readiness: `research-only`; live-signal generation blocked.
- Hypotheses: 85 total — 73 falsified, 7 infeasible, 5 formulated, 0 promoted.
- Experiments: 255 total — 253 completed, 2 designed.
- Evidence: 433 total — 168 weak, 236 moderate, 29 strong; 256 contradicting,
  168 inconclusive, 9 supporting. No candidate passes the promotion gate.
- Causal map: 69 refuted nodes, 0 promoted primitives, 0 causal edges.
- Service: disabled and inactive as of this snapshot.
- Repository: `main` is aligned with `origin/main`. The runner-owned graph drift
  through the final 2026-09-05T02:24Z cycle was provenance-audited and captured
  separately from the market-data recovery change.

### Last seven days of cycles

Window: 2026-08-29T03:11Z through 2026-09-05T03:11Z.

- 167 cycle reports.
- Every cycle found exactly 22 signals, generated/evaluated 0 hypotheses, and
  recorded `hypothesis_space_exhausted`.
- Every cycle reported 69 graph nodes and 0 edges.
- Every cycle skipped the same 2 unreplayable signals: cross-asset spread and
  weekend-volatility compression.
- One weekly ledger boundary (2026-09-03T00:44Z) registered 20 predictions and
  scored 20 prior predictions: 19 `confirmed_null`, 1 `inconclusive`, 0 edge.

## Why the loop exhausted

This is verified, not conjecture:

1. The main BTC and ETH scan caches ended at 2026-04-19T14:00Z. The cache layer
   returned them indefinitely, so all hourly scans used the same input.
2. Replaying that input produces 22 deterministic candidates: 7
   autocorrelation, 4 z-score mean reversion, 6 momentum persistence, 2
   volatility clustering, 1 return skew, 1 cross-asset spread, and 1 weekend
   volatility candidate.
3. All 22 current claim hashes resolve to `falsified` hypothesis records.
   `generate_hypotheses()` correctly drops resolved claims, leaving 0 work.
4. The 5 formulated top-up candidates cannot enter the current universe: 3 use
   excluded 4h data and 2 are SOL 1h candidates whose fetch returned 0 bars.

### Why SOL returned zero bars

`MarketData.fetch_ohlcv()` began deep-history pagination at 2015-01-01 and gave
up after 24 empty 1000-hour pages, around late 2017. Bitstamp's SOL/USD hourly
history begins in 2022, so the fetcher always stopped years before the listing.
This was a data-fetch defect, not a lack of SOL history.

## Recovery change

The market-data layer now:

- refreshes cached OHLCV tails once daily instead of freezing them forever;
- advances across arbitrarily long pre-listing empty history;
- retries provider errors, rejects partial histories and interval gaps, and
  fails visibly rather than silently using a stale cache;
- validates cached schema/order/continuity and writes replacements atomically;
- annotates returned frames with requested and exchange-native symbols.

Verification: 208 tests pass; ruff passes. Nine focused market-data regression
tests cover late listings, stale refresh, cache preservation, partial fetches,
gaps, explicit-since refresh, corrupt cache replacement, and provenance.
Opposing review is recorded at
`.reviews/market-data-supply-recovery-2026-09-05-v4.md`.

## Bounded new-supply experiment

One experiment only: **fresh, contiguous Bitstamp SOL/USD hourly history as a
new symbol-level information supply.** It is data expansion, not a new detector
or a relaxation of the promotion gate.

Predeclared isolated-probe gates:

1. at least 833 contiguous hourly bars;
2. last bar no more than 48 hours old;
3. at least one detected signal;
4. at least one unresolved SOL-derived candidate;
5. no write to production scientific state.

Result: **technical gate passed**. The isolated probe returned 35,488 contiguous
SOL/USD bars from 2022-08-18T12:00Z through 2026-09-05T03:00Z (0.42 hours old),
16 signals across seven methods, and 16 unresolved SOL-derived claim hashes.
Receipt:
`/opt/workspace/runtime/projects/atlas/recovery-probe-20260905-Zi8B1I/receipt.json`.

This proves useful new data exists. It does not authorize continuous service.

## Exact re-enable conditions

All conditions are required:

1. **Dataset identity is honest.** Either change hypothesis/prediction/evidence
   identity to the actual Bitstamp `*/USD` markets, with versioned migration of
   existing `*/USDT` records, or source genuine deep-history USDT markets.
   `DataFrame.attrs` alone is not durable scientific provenance.
2. **Novelty cannot be numeric wording drift.** Fresh BTC/ETH observations can
   change percentages/correlations embedded in claim text and thereby create a
   new hash for an already-falsified detector family. Add and test a stable
   hypothesis-family identity or an equivalent resolved-family guard before
   fresh-cache generation runs unattended.
3. Land and deploy the reviewed market-data change; `make check` and
   `make deploy-check` must pass from the deployed commit.
4. Re-enable only as a bounded 24-cycle canary with automatic stop/disable at
   the end. The first completed cycle must show fresh data for every admitted
   symbol, `hypotheses_evaluated > 0`, at least one SOL-derived hypothesis, no
   partial/stale-data fallback, and no `cycle.failed`.
5. Continue beyond the canary only if it produces at least one decisive
   research outcome (`kill`, `pivot`, or promotion-gate-qualified support) or a
   new scored forward observation. Twenty-four empty/no-hypothesis cycles are a
   failed experiment and return Atlas to parked state.

## Remaining bounded work

- Resolve the USD/USDT scientific identity boundary.
- Add stable family-level deduplication before daily cache refresh is deployed.
- The 3 formulated 4h hypotheses remain environmentally blocked; do not mark
  them permanently infeasible solely because 4h is absent from the current
  universe.
- Graph hygiene audit: the drift added 140 `live_observation` references across
  seven non-overlapping weekly buckets (20 each; 134 null confirmations, 4 edge
  appearances, 2 inconclusive). Every reference matches a resolved append-only
  prediction and authoritative evidence record; an independent backfill from
  runtime state reproduced the graph byte-for-byte. No recovery/readiness probe
  mutation was present.
