# Atlas — Scientific Causal Reasoning Engine

context-always-load:
  - CURRENT_STATE.md

Autonomous research system that uses the scientific method to build causal graphs of validated knowledge. The system generates its own hypotheses, designs and runs experiments, evaluates evidence, and makes promotion/kill decisions — without human intervention. Domain-agnostic architecture, currently applied to crypto markets.

**This is NOT a human-in-the-loop tool.** The CLI exists for development and debugging. Production Atlas runs as a continuous autonomous loop: signal intake → hypothesis generation → experiment execution → evidence evaluation → decision → graph update → repeat.

## Operating Principles

### How to Work in This Repo
- **Use `/review` after every significant feature, refactor, or architectural change.** Route to Codex for adversarial pressure testing. This is mandatory, not optional.
- **Use `/review` periodically on research methodology.** The system's hypothesis generation and statistical methods are as important to pressure-test as the code.
- **Pre-registered fields are immutable.** Hypothesis claims, falsification criteria, significance thresholds, and experiment parameters cannot change after creation. This is enforced in code.
- **Statistical claims must be honest.** Never claim a test adjusts for something it doesn't. If a test assumes iid/normal returns and crypto returns aren't, say so explicitly.
- **The causal graph earns its name or loses it.** Edges must represent tested causal claims, not correlations. If we can't justify causality, call it a dependency graph. Don't let branding outrun implementation.
- **Log methodology, not just results.** Record what search/generation methods produced each hypothesis, what worked, what didn't, and why. This is how the system learns to generate better hypotheses.
- **Default exchange is Bitstamp** for the runner (deep OHLCV pagination, 6+ years of 1h data). Kraken caps at ~720 bars per timeframe — insufficient for walk-forward validation. Binance and Bybit are blocked from the Hetzner US server.

### What NOT to Do
- Don't add speculative infrastructure. Build for the current autonomous loop, not hypothetical future ones.
- Don't confuse backtest performance with live performance. Backtests ignore fees, slippage, funding costs, and liquidity. Known limitation — address in Phase 2.
- Don't promote based on in-sample evidence alone. The promotion gate exists for a reason.
- Don't treat the causal graph as ground truth. It's a living model of validated beliefs, not reality. Primitives can be invalidated by future evidence.

## Architecture Governance

### Truth Sources
- **Reasoning Primitives**: Highest-trust. Validated claims promoted from experimental evidence via promotion gate.
- **Market Data**: External data from exchanges via ccxt. Trusted as factual but not interpretive.
- **Methodology Records**: How hypotheses were generated and what techniques worked. Trusted as operational history.
- **Forbidden**: Planning documents, hypotheses, and untested assumptions may NOT become truth sources.

### Session Model
- **Unit**: ResearchCycle — one hypothesis under active investigation
- **Lifecycle**: formulated → designing → experimenting → deciding → closed (promoted | killed | pivoted)
- **Reentry Snapshot**: current_hypothesis, active_experiments, evidence_collected, graph_summary, next_action

### Event Model
- Append-only JSONL per session in `sessions/`
- Types: `hypothesis_formulated`, `experiment_designed`, `experiment_executed`, `evidence_recorded`, `decision_made`, `primitive_promoted`, `graph_updated`, `methodology_logged`

### Artifact & Outcome Model
- **Artifacts**: Backtest results, statistical test outputs, causal graph snapshots, methodology reports
- **Decisions**: Explicit promote/kill/continue/pivot with rationale
- **Outcomes**: Linked back to the hypothesis and evidence that produced them

### Environments & Credentials
- `orchestration`: CLI, graph management, session control. No exchange credentials needed.
- `execution`: Data fetching, backtest runs. Exchange API keys scoped read-only, loaded from env vars only.
- No ambient credentials. Exchange keys via `ATLAS_EXCHANGE_API_KEY` / `ATLAS_EXCHANGE_SECRET`.

### Telemetry
- Session events serve as structured telemetry (append-only, timestamped, typed)
- MetaObservations recorded when: hypothesis fails unexpectedly, backtest produces surprising results, statistical assumptions violated, or generation method yields unusual hit rate

### Review Path
- Adversarial review on hypothesis formulation and experiment design before committing to execution
- Periodic review of autonomous loop methodology and statistical assumptions
- Route to opposing agent per workspace convention

## Promotion Gate: Evidence → Reasoning Primitive
- ≥2 strong evidence records
- ≥1 must be `out_of_sample_test` or `live_observation`
- Pre-registered significance threshold met
- Evidence from distinct experiments (not duplicate recordings)
- No unaddressed strong contradictory evidence

## Autonomous Loop Architecture

The production system runs as a continuous cycle:

```
1. SIGNAL INTAKE
   - Scan market data for anomalies, regime changes, structural patterns
   - Review academic literature, on-chain metrics, cross-asset correlations
   - Log methodology: what scanning techniques were used, hit rates

2. HYPOTHESIS GENERATION
   - Causal graph analysis: what nodes have weak/missing children? Where are the gaps?
   - Pattern synthesis from signals + existing primitives
   - Rank by testability and expected information gain, not speculation
   - Pre-register falsification criteria and significance threshold before any data

3. EXPERIMENT DESIGN & EXECUTION
   - Design bounded experiments with explicit success/failure criteria
   - Fetch data, run backtests, compute statistics
   - Train/test split or walk-forward validation (not in-sample only)

4. EVIDENCE EVALUATION
   - Classify evidence by class, quality, and direction
   - Link statistics directly to evidence records (not manual labels)
   - Check for contradictory evidence

5. DECISION
   - Promote (meets gate), kill (falsified), continue (more evidence needed), pivot (reformulate)
   - Record rationale

6. GRAPH UPDATE
   - Add new primitives, update edges
   - Identify invalidated primitives based on new contradictory evidence
   - Generate next-cycle suggestions from graph structure

7. METHODOLOGY LEARNING
   - Track which hypothesis generation methods produce promotable primitives
   - Track which experiment designs produce decisive evidence
   - Feed meta-observations into generation strategy
```

## Tech Stack
- Python 3.12, src layout, Click CLI (dev/debug), autonomous runner (production)
- ccxt (exchange data), pandas, scipy, statsmodels, networkx, pydantic
- Venv at `.venv/` — always use `.venv/bin/atlas` or `.venv/bin/python`

## Development
```bash
cd /opt/workspace/projects/atlas
.venv/bin/pip install -e .
.venv/bin/atlas --help
.venv/bin/atlas scan --symbol BTC/USDT --timeframe 4h   # Debug: inspect signals
.venv/bin/atlas run --once                                # Run one autonomous cycle
.venv/bin/atlas run --interval 3600                       # Continuous operation
.venv/bin/atlas status                                    # Current state
.venv/bin/atlas graph show                                # Causal graph
.venv/bin/pytest                                          # Tests (pytest in .venv)
```

## Architecture & Code Map

```
src/atlas/
├── models/           # Pydantic domain objects for the research loop
│   ├── hypothesis.py   # CriticalAssumption specialization — falsifiable claim + pre-registered alpha
│   ├── experiment.py   # Probe specialization — bounded test with success/failure criteria
│   ├── evidence.py     # Typed observation: class (backtest/OOS/live/etc), quality, direction
│   ├── primitive.py    # ReasoningPrimitive — validated TruthSource, node in causal graph
│   ├── graph.py        # CausalGraph — networkx DiGraph wrapper with display/serialization
│   ├── session.py      # ResearchCycle + ReentrySnapshot
│   └── events.py       # Append-only SessionEvent types
├── generation/       # Autonomous hypothesis generation
│   ├── signals.py      # Market data signal detectors (regime change, autocorrelation, mean reversion, volume)
│   └── hypotheses.py   # Signal→Hypothesis converters + graph gap analysis
├── analysis/         # Experiment execution
│   ├── backtest.py     # Vectorized backtest with fee model + anchored walk-forward validation
│   └── statistics.py   # Sharpe significance, t-test, block bootstrap CI (two-sided, preserves serial dependence)
├── data/
│   └── market.py       # ccxt wrapper with CSV cache (key includes exchange_id)
├── storage/
│   ├── state_store.py  # Shared state management with pre-registration immutability
│   ├── event_store.py  # Append-only JSONL per session
│   └── graph_store.py  # Causal graph JSON persistence
├── runner.py         # AutonomousRunner — the production loop (scan→generate→test→evaluate→decide)
└── cli.py            # Click CLI — manual workflow + `atlas run` for autonomous mode
```

### Key Design Decisions (settled, don't re-derive)
- **Hypothesis IDs are SHA-256 hashes of the canonicalized claim text.** `claim_canonical()` in `utils.py` normalizes: lowercase, whitespace-collapse, strip trailing punctuation. `claim_hash()` applies canonical form then hashes. This prevents wording drift from forking logically identical hypotheses. Schema version 2 (migrated 2026-04-18).
- **Walk-forward validation replaces single 70/30 split.** Anchored expanding window with 5 OOS folds. Concatenated OOS returns used for statistical tests. Signal scan still restricted to training data only.
- **Fee model: 26 bps (Kraken taker) deducted on every position change.** One-way cost of `fee_bps / 10_000` per position change; a full round trip costs 52 bps. Default 0 for unit tests, 26 in runner.
- **Bonferroni correction is applied per cycle.** Alpha is divided by the number of hypotheses tested in a cycle. See `generate_hypotheses()` in `runner.py`.
- **Evidence quality requires BOTH Sharpe significance AND bootstrap significance** for "strong" classification. Single-test significance only earns "moderate".
- **Promotion gate blocks on ANY strong contradictory evidence** and requires evidence from distinct experiments (not duplicate recordings).
- **Pre-registered fields are immutable.** `_save_obj()` in `cli.py` enforces this for hypotheses and experiments. The runner bypasses this (it writes directly) — this is a known gap; see below.
- **Default exchange is Bitstamp.** Provides deep OHLCV history via pagination (99K+ 1h bars for BTC). Kraken caps at ~720 bars regardless of `since` parameter — below the 833-bar walk-forward minimum. Binance and Bybit are geo-blocked from the Hetzner US server (Hillsboro, OR).
- **Evidence ID is deterministic.** `sha256(hyp_id + ":" + exp_id + ":" + block_content_hash)[:16]`. Two concurrent workers ingesting the same file compute the same ev_id; last-write-wins is benign (same logical content). The `source_hash` field (`sha256[:16]` of the raw YAML block) acts as a content snapshot — a post-ingest edit produces a different ev_id, surfacing the mutation as a new record rather than silently overwriting.
- **StateStore writes are atomic.** `save()` writes to a tmpfile then renames via `os.replace`. Readers never observe a partial write.
- **Revalidation queue is append-only.** `due_revalidations()` deduplicates by experiment_id at read time, so concurrent or repeated appends don't produce duplicate scheduled re-runs. Known gap: file locking is not implemented; the single-process assumption holds for production use.

### State Storage
- `.atlas/hypotheses/` — JSON per hypothesis (keyed by claim hash)
- `.atlas/experiments/` — JSON per experiment
- `.atlas/evidence/` — JSON per evidence record
- `.atlas/cycles/` — JSON per research cycle
- `.atlas/primitives/` — JSON per reasoning primitive
- `sessions/` — JSONL append-only event logs (gitignored)
- `graph/causal_graph.json` — networkx JSON (tracked in git)
- `data/` — CSV market data cache (gitignored)
- `reports/` — Cycle reports from autonomous runs (gitignored)
- `methodology.jsonl` — Methodology learning log (gitignored)

## Adversarial Review History

Two Codex reviews completed. All critical and high findings addressed.

### Review #1 (bootstrap commit) — 9 findings
| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | Critical | Promotion gate ceremonial — labels not verified | Deferred (Phase 2: auto-link stats to evidence) |
| 2 | Critical | Pre-registration not immutable | **Fixed** — immutability guard in `_save_obj()` |
| 3 | Critical | Session model ambiguous with >1 active cycle | **Fixed** — warns on ambiguity |
| 4 | High | File storage not crash/concurrency safe | Deferred (single-user CLI for now) |
| 5 | High | OOS is metadata only, not enforced | **Fixed** — runner now does real IS/OOS split |
| 6 | High | Statistical tests assume iid, false Lo(2002) claim | **Fixed** — honest docstrings |
| 7 | High | Backtest ignores friction | Deferred (Phase 2: fee model) |
| 8 | Medium | "Causal" graph is really a belief DAG | **Fixed** — missing parents error, children tracked |
| 9 | Medium | Cache key omits exchange_id | **Fixed** |

### Review #2 (autonomous loop) — 5 findings
| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | Critical | No durable hypothesis identity | **Fixed** — claim hash IDs |
| 2 | Critical | OOS contaminated by signal scan | **Fixed** — scan IS only |
| 3 | High | No multiple testing correction | **Fixed** — Bonferroni |
| 4 | High | Promotion gate weaker than documented | **Fixed** — distinct experiments + contradictions block |
| 5 | Medium | Split-brain state between CLI and runner | **Fixed** — shared `StateStore` with immutability enforcement |

### Review #3 (state store + tests + block bootstrap) — 4 findings
| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | Critical | Bonferroni `_bonferroni_n` is process-local, lost on restart | **Fixed** — persisted as `bonferroni_n` and `adjusted_alpha` in experiment parameters |
| 2 | High | StateStore read-check-write has no locking (concurrent access) | Deferred — single-process for now |
| 3 | High | Immutability guard bypassable by omitting fields from save data | **Fixed** — omission of existing immutable fields now raises ValueError |
| 4 | High | Bootstrap one-sided: only tests positive Sharpe, never flags negative strategies | **Fixed** — two-sided p-value and CI-excludes-zero significance |

### Review #4 (fee model + walk-forward) — 6 findings
| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | Critical | Walk-forward computes unused train_signals, doesn't carry fitted state to OOS | **Fixed** — removed unused train_signals (current signal builders are stateless rolling indicators) |
| 2 | High | Fee model double-charges: 2*fee_bps per change instead of 1*fee_bps | **Fixed** — now charges fee_bps/10_000 per position change (one-way) |
| 3 | High | mean_oos_sharpe disagrees with concatenated-returns Sharpe used in stat tests | **Fixed** — added aggregate_oos_sharpe from concatenated returns, used for decisions |
| 4 | High | StateStore no file locking for concurrent access | Deferred — single-process for now |
| 5 | Medium-High | Bootstrap p-value not centered on null (resamples from empirical dist with mean) | Known limitation — bootstrap CI used alongside parametric test, not alone |
| 6 | Medium | Fold size guard (10 bars) below signal warm-up requirements (20-50 bars) | **Fixed** — raised minimum to 50 bars per fold |

## Known Gaps & Next Steps (Priority Order)

### Completed
1. ~~**Runner should use shared state management with CLI.**~~ **Done** — `storage/state_store.py` with immutability enforcement, used by both CLI and runner. Bonferroni adjustment no longer mutates the pre-registered `significance_threshold` on the hypothesis model.
2. ~~**Tests.**~~ **Done** — 47 tests across 5 files: state store immutability, backtest math (fees + walk-forward), statistical tests, signal detectors, promotion gate logic.
3. ~~**Block bootstrap.**~~ **Done** — Stationary block bootstrap with geometric block lengths (default block_size=sqrt(n)). Preserves serial dependence in crypto returns.

### Near-term (Phase 2)
4. **More signal detectors.** On-chain metrics, cross-asset correlations, funding rate signals, orderbook imbalance. The signal→hypothesis pipeline is modular — add new detectors in `generation/signals.py`.
5. ~~**Walk-forward validation**~~ **Done** — Anchored expanding window with 5 OOS folds. Runner uses walk-forward instead of single 70/30 split. Statistical tests run on concatenated OOS returns.
6. ~~**Fee/slippage model in backtest.**~~ **Done** — `fee_bps` parameter on `run_backtest()` and `walk_forward_backtest()`. Deducts one-way cost per position change. Runner passes 26 bps (Kraken taker).
7. **Automated evidence verification.** Link experiment statistical output directly to evidence records instead of relying on quality classification logic.
8. **Systemd service** for continuous autonomous operation.
9. **Cache invalidation.** Market data CSVs are cached indefinitely — need freshness policy for repeated cycles.

### Longer-term (Phase 3)
10. **Proper causal inference.** Granger causality tests, intervention analysis, or structural equation models to justify "causal" edges rather than manual belief links.
11. **Live signal generation** from validated primitives → trading signals.
12. **Risk management layer** — position sizing, correlation-aware portfolio construction.
13. **Methodology meta-learning** — analyze `methodology.jsonl` to learn which generation methods and experiment designs produce promotable primitives.
