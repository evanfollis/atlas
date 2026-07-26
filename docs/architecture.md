# Atlas architecture

Real composition, dependency direction, artifact roles, runtime paths, and
deployment/containment posture (ADR-0050 §2 front door). Not a marketing
overview. Derived from the import graph and live telemetry, not filenames.

## Shape and lifecycle

- **shape**: `service` — an autonomous systemd loop (`atlas-runner.service`).
- **lifecycle**: `active` — running in production.
- **agentic_risk**: `agentic` — unattended, root-running, self-writing loop
  that makes/commits decisions without per-cycle human review. It executes no
  model-controlled/LLM code, so untrusted-model-output containment is largely
  N/A; the operational-autonomy risk is real and tracked (see §Agentic safety).

## Composition roots and dependency direction

Two composition roots:

- `src/atlas/runner.py::AutonomousRunner.run_continuous` — production loop
  (scan → generate → walk-forward test → decide → graph update → score). ~2.1k
  LOC monolith; splitting it is a later, verified-seam-only migration.
- `src/atlas/cli.py::cli` (Click) — dev/debug; the `atlas` entrypoint.

Internal imports form a clean, acyclic, downward-only layering (verified):

```
models/      leaf domain types (hypothesis, evidence, experiment, graph,
             primitive, prediction, session, events)
   ▲
storage/     event_store, graph_store, prediction_store, state_store
   ▲            (each depends only on its matching models type)
   ├── generation/  signals → {calendar, composite, hypotheses}
   ├── analysis/    backtest, statistics (+ stationarity, event_study: research)
   ├── adapters/discovery/  canon projection (emit, migrate) — manual/standalone
   ├── research/ingest      CLI-only ingestion
   └── graph_backfill
          ▲
   runner.py / cli.py  (composition roots)
```

No `models/` or `storage/` module imports upward. Composition roots may depend on
domain + adapters; domain code depends on neither deployment nor UI.

**Wired into the live loop**: runner + generation.{signals,calendar,composite,
hypotheses} + analysis.{backtest,statistics} + data.{market,alternative} +
models.* + storage.* + graph_backfill + utils.

**Test-covered but not in the loop** (research tools): `data.events`,
`analysis.event_study`, `analysis.stationarity`. **Dormant** (imported by
nobody): `data.dune`, `data.derivatives`. **Manual/standalone**:
`adapters/discovery/*` (canon projection), `research/ingest`,
`scripts/migrate_claim_hash.py`. These are candidates for an explicit
`experiments/` or historical relocation in a later phase.

## Artifact roles (ADR-0050 §5)

| Role | Paths | Tracked? |
| --- | --- | --- |
| authoritative | `src/`, `tests/`, `docs/`, `deploy/`, `scripts/`, `pyproject.toml`, `repo.toml`, `Makefile`, `AGENTS.md`, `CLAUDE.md`, `README.md` | yes |
| runtime | `.atlas/`, `sessions/`, `reports/`, `data/`, `predictions.jsonl`, `methodology.jsonl`, `pending_revalidation.jsonl` | no (gitignored) |
| generated | `.canon/` (projection of `.atlas/`), `index.md` | **tracked (defect)** |
| historical | `findings/`, `.reviews/` | yes |

Known unresolved tensions (deferred migration items, not silently accepted):

- **`graph/causal_graph.json`** is tracked yet rewritten by the live runner
  every cycle — runtime-role in practice, authoritative-in-Git by history. It is
  deliberately omitted from `repo.toml [artifacts]` (a validator would reject
  either role). Resolution options: an append-only/reviewed write guard behind
  `make check`, or externalization to the runtime root. Requires coordinating
  with the live writer; not done in the first pass. The clean-check gate treats
  it as the one authorized dirty path.
- **`.canon/` (315 files) and `index.md` are tracked but generated**, and
  `.canon/` is stale vs `.atlas/`. Demoting them to gitignored/generated needs a
  canon-owner (ADR-0026) decision and consumer check; deferred.

## Runtime state and paths

Hosted runtime state currently lives in the repo working tree (`.atlas/`,
`sessions/`, `reports/`, root `*.jsonl`) and at the workspace telemetry sink
`/opt/workspace/runtime/.telemetry/events.jsonl`. The target convention is
`/opt/workspace/runtime/projects/atlas/`. Externalizing the in-tree runtime
state is a compatibility migration (per-path mapping + the live writer +
rollback) and is deferred; this pass externalizes only the previously-hardcoded
telemetry/handoff paths behind config (defaults preserve current behavior).

## Deployment

- Unit: `deploy/atlas-runner.service` (mirrored to `/etc/systemd/system/`).
  Deploy = `systemctl restart atlas-runner.service`; no push-to-main webhook.
- The service runs one cycle on start, then hourly. Restart is a clean canary:
  verify a `cycle.completed` + graph write + telemetry emission, keep the prior
  unit as rollback.

## Agentic safety posture (ADR-0050 §8 / ASG register)

Atlas is `agentic` but runs no model-controlled code. Applicable open dated
exceptions in `supervisor/system/agentic-safety-gap-register.md`:

- **ASG-001** (root execution): the service runs as root. Non-root identity is
  host-wide ADR-class work (ownership migration of `.atlas/`, graph, venv,
  telemetry), explicitly out of scope for this repo refactor.
- **ASG-002** (containment): systemd filesystem hardening is being added to the
  unit; process/network default-deny is fleet-wide work.
- **ASG-003** (ambient credentials): only secret is `DUNE_API_KEY` (for the
  dormant Dune module); no exchange keys (public Bitstamp OHLCV).
- **ASG-004** (trajectory/outcome evidence — repo-specific, required for
  conformance): Atlas satisfies the substance as follows —
  - **run/session identity**: `ResearchCycle` is the session unit; append-only
    JSONL event logs under `sessions/`.
  - **outcome witness**: decisions are backed by typed `Evidence` records +
    walk-forward OOS stats + the forward-prediction ledger (`predictions.jsonl`
    scored to `live_observation` evidence), not by completion text.
  - **trace retention**: append-only telemetry to the workspace sink with
    `sourceType=system`; `methodology.jsonl` records generation methods.
  - **resume semantics**: durable `StateStore` (atomic tmpfile+rename) +
    append-only ledgers; the loop re-derives state on restart; the S3-P2
    escalation counter persists across restarts and telemetry rotation.
  - **incident-derived regression cases**: the S3-P2 gate carries regression
    tests for its historical bug classes (rotation, double-emit, staleness
    re-arm, corrupt-state fail-toward-signal).

## Type-and-lint ramp

`make lint` (ruff: E9 + F + B, minus F841/B007) is green and required in
`check`. `make typecheck` (mypy) currently covers `models/` + `storage/` only
and is **advisory** (not in `check`): strict typing of the 2.1k-line runner and
the numeric analysis modules is a later proportionate ramp. F841/B007
(unused-local/loop-var) findings — mostly in dormant research modules — are the
first cleanup ramp.

## Honest status

0 promoted primitives, 0 causal edges, 69 refuted nodes. The system is a working
falsification engine that has correctly promoted nothing yet; see
`docs/CASE_STUDY.md`.
