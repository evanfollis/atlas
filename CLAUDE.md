# Atlas — Scientific Causal Reasoning Engine

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
- **Default exchange is Kraken.** Binance and Bybit are blocked from the Hetzner US server.

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
- Python, src layout, Click CLI (dev/debug), autonomous runner (production)
- ccxt, pandas, scipy, statsmodels, networkx, pydantic

## Development
```bash
cd /opt/projects/atlas
.venv/bin/pip install -e .
.venv/bin/atlas --help
.venv/bin/pytest
```
