---
name: Atlas README
description: Autonomous scientific-method research loop that builds a causal graph of validated market claims via pre-registration, walk-forward OOS, and a code-enforced promotion gate
type: reference
updated: 2026-07-26
---

# Atlas

**What is this?** Atlas is an autonomous **scientific-method research loop**. It
generates falsifiable hypotheses, pre-registers a falsification criterion and
significance threshold, runs walk-forward out-of-sample experiments, records
typed evidence, and makes an explicit promote / kill / continue / pivot
decision — building a causal graph of *validated* claims (not free-text
associations). The core is domain-agnostic; the current application is crypto
markets (Bitstamp hourly BTC/ETH/SOL). It runs unattended as a systemd service;
the CLI exists for development and debugging. It contains no in-product LLM code.

**Lifecycle.** `active` (deployed). This is the one canonical implementation;
there is no successor. An earlier, unrelated differentiable-programming
exploration (`crypto-agent-dp-lab`) is an archived predecessor, not a successor —
its thesis was never validated.

**What is verified today — and what is not claimed.**

- Verified: 191-test hermetic suite green; the promotion gate, walk-forward
  math, statistical tests, the forward-prediction ledger/scorer, and the S3-P2
  escalation gate all have coverage; the loop runs autonomously and scores its
  forward predictions unattended.
- **Not claimed**: any validated market edge. The promotion gate has **never
  fired** — 0 promoted primitives, 0 causal edges, 69 refuted nodes. The only
  scientific output to date is *negative* knowledge (falsifications and
  confirmed-null forward windows). Backtests model a 26 bps fee but ignore
  slippage/funding/liquidity: backtest ≠ live. See `docs/CASE_STUDY.md`.

**Fastest meaningful check.**

```bash
make setup    # create/refresh .venv (Python 3.11+)
make check    # lint + hermetic tests + repo/clean/prompt validation
```

`make help` lists all targets. Tests need no network or credentials.

**Where to go deeper.**

- `docs/architecture.md` — composition roots, dependency direction, artifact
  roles, runtime paths, deployment, and agentic-safety posture.
- `docs/CASE_STUDY.md` — outsider-legible, truthful account of what has and
  hasn't been demonstrated.
- `AGENTS.md` — concise agent/contributor instructions; `CLAUDE.md` — full
  governance and promotion-gate rules.
- `repo.toml` — shape/lifecycle/risk declaration (ADR-0050).

## Repository layout

- `src/atlas/` — library + CLI: `models/` (domain), `storage/`, `analysis/`,
  `data/`, `generation/`, `adapters/`, plus `runner.py` (the loop) and `cli.py`.
- `tests/` — hermetic pytest suite.
- `deploy/` — systemd unit (`atlas-runner.service`).
- `findings/`, `.reviews/` — historical research log and adversarial reviews.
- `scripts/` — operator tooling (`check_repo.py`, `deploy-check.sh`,
  `migrate_claim_hash.py`) and older one-off research scripts.
- Runtime state (`.atlas/`, `sessions/`, `reports/`, `data/`, root `*.jsonl`) is
  gitignored and created on use. `graph/causal_graph.json` is tracked and
  rewritten by the live runner — see `docs/architecture.md`.

## Promotion gate

A claim becomes a promoted reasoning primitive only with ≥2 strong evidence
records from distinct experiments, at least one out-of-sample or live, meeting
the pre-registered threshold, with no unaddressed strong contradiction. Enforced
in code. Pre-registered fields are immutable.

## Suggested GitHub metadata

- **Description:** Autonomous scientific-method research loop building a causal graph of validated market claims (pre-registration, walk-forward OOS, code-enforced promotion gate).
- **Topics:** `causal-reasoning`, `scientific-method`, `hypothesis-testing`, `pre-registration`, `walk-forward`, `falsification`, `autonomous-agent`, `quant-research`, `python`.
