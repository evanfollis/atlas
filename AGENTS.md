# Atlas — agent instructions

Provider-neutral front door (ADR-0050). Concise by design; deep policy lives in
`CLAUDE.md` (still the ADR-0021 `context-always-load` source — see below) and
`docs/architecture.md`.

## Purpose and scope

Atlas is an autonomous **scientific-method research loop**: it generates
falsifiable hypotheses, pre-registers a falsification criterion + significance
threshold, runs walk-forward experiments, records typed evidence, and makes an
explicit promote / kill / continue / pivot decision — building a causal graph of
*validated* claims. Domain-agnostic core, applied to crypto (Bitstamp 1h
BTC/ETH/SOL). It runs unattended as a systemd service; the CLI is for dev/debug.
It contains **zero in-product LLM/prompt code** (deterministic Python).

## Real commands

`make help` lists everything. Key: `make check` (full gate: lint + tests +
repo/clean/prompt validate), `make test`, `make lint`, `make run` (one cycle),
`make deploy-check`. Use `.venv/bin/python -m <tool>` — the venv script shebangs
are stale (known gotcha). Tests are hermetic (no network/credentials).

## Hard boundaries

- **Pre-registered fields are immutable** (claim, falsification criteria, alpha,
  experiment params). Enforced in `StateStore`. Never relax.
- **Statistical honesty**: never claim a test adjusts for something it doesn't.
- **The graph earns "causal" or loses it**: edges must be tested causal claims,
  not correlations. Today it holds only refuted nodes + 0 promoted primitives.
- **Promotion gate** (≥2 strong distinct-experiment evidence, ≥1 OOS/live,
  pre-registered threshold met, no unaddressed strong contradiction) is enforced
  in code and must not be weakened.
- **`_maybe_escalate_frozen_loop` (S3-P2) requires `adversarial-review.sh`
  before any commit** — it has a long bug history. No exceptions.
- **Default exchange is Bitstamp** (deep history; Binance/Bybit geo-blocked).

## Where to load more

- Architecture, dependency direction, artifact roles, runtime paths, deploy
  shape, agentic-safety posture: `docs/architecture.md`.
- Current operational state: `CURRENT_STATE.md`.
- Full governance/charter (and the `context-always-load` block the ADR-0021
  SessionStart hook still reads): `CLAUDE.md`. **CLAUDE.md remains the loader
  until the hook is upgraded to read AGENTS.md first** (documented ADR-0021
  compatibility exception; do not move the load block yet).

## Dirty-tree and deploy cautions

- `graph/causal_graph.json` is **rewritten every cycle by the live runner**. It
  is the one path allowed to be dirty; never hand-edit it, and do not `git add`
  it into unrelated commits. Commit runner-owned graph drift separately.
- `.atlas/`, `sessions/`, `reports/`, `data/`, and the root `*.jsonl` files are
  runtime state (gitignored). Do not commit them.
- Deploy = `systemctl restart atlas-runner.service` (local systemd; no
  push-to-main webhook). "Pushed" is not "deployed." Canary + verify a cycle
  after restart; keep rollback.
- Containment posture is `agentic` with open dated exceptions ASG-001..004
  (root execution etc.) in `supervisor/system/agentic-safety-gap-register.md`.

## Definition of done

`make check` green from a clean checkout; changed prompt/instruction surfaces
eval-governed (ADR-0039); production changes carry a real-outcome verification
receipt and rollback; CURRENT_STATE.md updated.
