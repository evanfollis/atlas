# Event-Study Infrastructure + First-Pass Results — 2026-04-12

**Phase B1 infrastructure finding, not a promoted primitive.** Built the curated-events dataset and event-study framework; first-pass daily-return CAR tests on BTC are directionally sensible but **underpowered by construction** (n=1–3 per category). This finding exists to document the infrastructure and to set the scope for what the curated list needs next.

## What was built

- `src/atlas/data/events.py` — 17 curated events across 6 categories (halving, fork/merge, regulatory, collapse, listing, macro). Each entry carries date (UTC), scope (assets affected), label, and primary-source citation. Curation rule: precision over recall, add only dates verifiable against at least one primary source.
- `src/atlas/analysis/event_study.py` — per-event path matrix, per-event CAR over caller-specified [k0, k1], empirical two-sided p-value vs. matched-control CAR distribution drawn from non-event windows (with ±buffer exclusion).
- 6 tests (`tests/test_events.py`): planted-shock detection, null-DGP non-rejection, bad-window + edge-event validation.

## First-pass results: BTC daily CAR[0, +20] post-event

| Category | n | mean CAR | median CAR | p (two-sided) |
|---|---|---|---|---|
| halving     | 3 | +1.2% | −1.1% | 0.92 |
| regulatory  | 3 | +7.7% | +12.5% | 0.56 |
| collapse    | 3 | −21.1% | −21.4% | 0.21 |
| macro       | 2 | +15.5% | +15.5% | 0.30 |
| fork        | 1 | +35.7% | +35.7% | 0.06 |

Every category has n ≤ 3. None reaches conventional significance. Directions line up with priors — collapses drag BTC down, regulatory clarity and recoveries lift it — but this is storytelling over a handful of observations, not evidence.

## Why this was expected

The curated list is deliberately small. A halving happens once every four years; regulator actions of the size worth cataloging are rarer still. To power a formal event-study test at α=0.05 we'd need n ≥ 15–20 per category *within the same asset*, which a curated macro-event list cannot provide.

## Actionable next steps

1. **Narrow the horizon**, don't expand the event list. Intraday windows around each event give many bars of observation per event; daily CAR throws most of that away. Liquidation cascades, funding-reset events (Phase B2), and exchange outages are the right *class* — high-frequency, event-rich, single-asset — to power the framework. Phase B1's curated macro list serves as a sanity check and anchor, not as a testbed for trading signals.

2. **Pool across assets where the event is asset-agnostic.** COVID / SVB / FTX hit BTC and ETH together; pooling doubles the effective n without compromising independence much (returns are highly correlated in crisis).

3. **Resist adding marginal events to juice n.** Every unverified event dilutes the primary-source discipline that makes the dataset trustworthy. Better to accept low statistical power on the structured list and route inference to higher-frequency event streams.

## What this is NOT

- It is **not** evidence that events move BTC. p > 0.05 in every category.
- It is **not** a claim that the framework is broken — the planted-shock test passes and the null test fails to reject, both as designed.
- It is **not** a reason to postpone Phase B2 (liquidation events); on the contrary, the n-limit here is the argument for moving to higher-frequency event sources.

Script: `scripts/events_btc_car.py`.
