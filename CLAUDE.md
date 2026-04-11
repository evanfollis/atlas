# Atlas — Scientific Causal Reasoning Engine

Systematic research platform using the scientific method to build causal graphs of validated knowledge. Domain-agnostic architecture, currently applied to crypto markets.

## Architecture Governance

### Truth Sources
- **Reasoning Primitives**: Highest-trust. Validated claims promoted from experimental evidence via promotion gate.
- **Market Data**: External data from exchanges via ccxt. Trusted as factual but not interpretive.
- **Forbidden**: Planning documents, hypotheses, and untested assumptions may NOT become truth sources.

### Session Model
- **Unit**: ResearchCycle — one hypothesis under active investigation
- **Lifecycle**: formulated → designing → experimenting → deciding → closed (promoted | killed | pivoted)
- **Reentry Snapshot**: current_hypothesis, active_experiments, evidence_collected, graph_summary, next_action

### Event Model
- Append-only JSONL per session in `sessions/`
- Types: `hypothesis_formulated`, `experiment_designed`, `experiment_executed`, `evidence_recorded`, `decision_made`, `primitive_promoted`, `graph_updated`

### Artifact & Outcome Model
- **Artifacts**: Backtest results, statistical test outputs, causal graph snapshots
- **Decisions**: Explicit promote/kill/continue/pivot with rationale
- **Outcomes**: Linked back to the hypothesis and evidence that produced them

### Environments & Credentials
- `orchestration`: CLI, graph management, session control. No exchange credentials needed.
- `execution`: Data fetching, backtest runs. Exchange API keys scoped read-only, loaded from env vars only.
- No ambient credentials. Exchange keys via `ATLAS_EXCHANGE_API_KEY` / `ATLAS_EXCHANGE_SECRET`.

### Telemetry
- Session events serve as structured telemetry (append-only, timestamped, typed)
- MetaObservations recorded when: hypothesis fails unexpectedly, backtest produces surprising results, statistical assumptions violated

### Review Path
- Adversarial review on hypothesis formulation and experiment design before committing to execution
- Route to opposing agent per workspace convention

## Promotion Gate: Evidence → Reasoning Primitive
- ≥2 strong evidence records
- ≥1 must be `out_of_sample_test` or `live_observation`
- Pre-registered significance threshold met
- Human review attached

## Tech Stack
- Python, src layout, Click CLI
- ccxt, pandas, scipy, statsmodels, networkx, pydantic

## Development
```bash
pip install -e .
atlas --help
pytest
```
