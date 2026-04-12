# Research Backlog — Atlas

Ordered by codex review #7 recommended sequence (2026-04-12). Do infrastructure that unblocks multi-class work before opening the heaviest new data channels.

## Phase A — Infrastructure (do first)

**A1. Extend walk-forward harness to support fit-on-train / apply-on-test.** Add `signal_builder(train_df, test_df)` dual-arg form (opt-in by arity inspection); keep stateless form working. Unblocks trainable-class experiments, which matter much more for event/news signals than for lag-6. Codex flagged this as the single most-valuable next code change.

**A2. Rolling stationarity + structural-break diagnostics.** Replace calendar-year bins (codex #5 critique) with rolling-window β estimate + CI, CUSUM / Chow test helpers, regime-labelled subsample reporter. Lives in `atlas/analysis/`.

**A3. Maker-fee / venue-cost models in backtest.** Currently a single `fee_bps` parameter. Add maker vs taker + venue tier table so strategies can be evaluated under best-case execution.

## Phase B — Structured events (do after A1, A2)

**B1. Events data source — structured first.** Halvings, forks, protocol upgrades, SEC/regulatory dates, listings/delistings, major exchange outages, liquidation cascade timestamps. Curated small dataset, not raw news. Event-study framework: pre/post return windows around each event, matched-control returns, cumulative abnormal returns.

**B2. Liquidation / funding-reset events.** From Deribit + CoinGlass free tier + BitMEX liquidation stream. Different from funding-level signal — focus on timestamped reset *events* as event study, not continuous series.

## Phase C — On-chain (after B shows signal class is worth heavier data plumbing)

**C1. Dune exchange net-flow.** CEX addresses already cached (4957 labels). Needs a query for daily inflows/outflows by CEX tier, free-tier rate limits respected.

**C2. Dispersion narrow retest (codex #6 design).** Fix venue membership to BitMEX+KrakenFutures only, 8h settlement cadence, residualize dispersion against mean funding, test as interaction `mean_fund × z(disp)` not median gate.

## Phase D — Portfolio & text (last)

**D1. Independent-edges portfolio framework.** Only useful once 2-3 weak but plausible edges exist. Combined sharpe scales √N with per-signal turnover flat.

**D2. Raw news text ingestion.** CryptoPanic / RSS aggregators. LLM-based claim extraction with strict schema. Heaviest mechanism class, least forgiving of out-of-band evaluation — do last.

**D3. Substack as signal source.** Two distinct pipelines per user's mandate: (a) idea sourcing → hypothesis generation, (b) timestamped author calls as signals themselves with forward-return track record per author.

## Parked (do not open without new mechanism)

- Lag-6 cross-asset reversal, BTC→ETH 4h retail: closed after 3 cycles (stateless → trainable → low-turnover). Reopen only with maker-only sub-4h execution OR alternate asset pair (newer majors: SOL/TAO/TIA) OR ex-ante regime gate mechanism.
- DVOL 60-80% bucket: killed on OOS episode-adjusted test. Do not reopen.
- Funding dispersion as standalone predictor: null. Reopen only after A1 + dispersion narrow retest.

## Completed this session
- Phase A2: rolling stationarity + structural-break diagnostics (`stationarity.py` + 10 tests)
- Lag-6 re-examined via Phase A2 tooling (`2026-04-12_lag6_decay.md` stationarity section)
- Phase A3: maker/taker fee model + VENUE_FEES table
- Codex review #8: CUSUM rule unified; fee accounting fixed for reversals; maker/taker partial-config fail-closed; lag-6 Chow post-selection caveat
- Phase B1: curated events dataset + event-study framework (`2026-04-12_events_first_pass.md`)

- DVOL rebuttal test: killed the bucket (`2026-04-12_dvol_killed.md`)
- Regime-gated funding reversal: effect lives in wrong direction, non-stationary (`2026-04-12_funding_gated.md`)
- Dispersion-as-gate: partial positive with venue-membership caveat (`2026-04-12_dispersion_as_gate.md`)
- Trainable-signal control: turnover cost dominates (`2026-04-12_trainable_control.md`)
- Low-turnover lag-6 expression: no robust IS-selectable rescue found (`2026-04-12_lowturn_lag6.md`)
- Silent-failure hardening of DerivativesData + DuneClient
- Persistent methodology memory with 5 portable rules
