# Atlas → canon mapping (v1)

This document explains the atlas → L1 discovery-framework canon mapping
implemented in `emit.py`. The canonical machine-readable form is the Policy
object emitted by `emit_policy_tier_mapping()` — this markdown is the human
explanation.

## Spec version

Canon: **0.1.0** (`/opt/workspace/projects/context-repository/spec/discovery-framework/`)
Atlas: Hypothesis schema v2 (claim-hash IDs, migrated 2026-04-18)

## Object mappings

### Hypothesis → Claim

| Atlas field | Canon field | Transform |
|---|---|---|
| `id` (sha256[:16] of claim_canonical) | `id` | identity |
| `claim` (str) | `statement` (str) | identity — both immutable |
| `falsification_criteria` (str) | `falsification_criteria` (array[str], ≥1) | wrap as `[str]` |
| `significance_threshold` (float) | `thresholds.alpha` (number) | identity |
| `domain` (str, default "crypto") | (not mapped to Claim) | stored in local metadata only |
| `tags` (array[str]) | (not mapped) | |
| `status` (HypothesisStatus) | NOT on Claim — emit via EventLogEntry.phase_transition | FORMULATED→draft, TESTING→probe, {SUPPORTED,FALSIFIED,PROMOTED}→promotion |
| `rationale` (str) | (not mapped to Claim; shown in Decision.rationale) | |
| `created_at` (datetime) | `emitted_at`, `role_declared_at` (iso Timestamp) | identity |
| `parent_primitive_id` | (not mapped to Claim) | reserved for future `successor_claim_id` on Decision |

**Required canon Claim fields supplied by the adapter (not from atlas):**

- `spec_version` = `"0.1.0"`
- `object_type`  = `"Claim"`
- `emitter`      = `"L3:atlas"`
- `layer`        = `"L3"`
- `roles`        = `["Claim"]`
- `binding`      = `"binding"` (domain-layer; non-meta; see canon.md)
- `sources`      = `[]` (atlas doesn't currently cite upstream canon)
- `exposure`     = minimal default — see `_default_exposure()` — atlas
  research commits no capital
- `artifact`     = `ArtifactPointer` to `.atlas/hypotheses/<id>.json` if
  present on disk (content_hash + mtime version)
- `instance_id`  = `"atlas"`

### Evidence → Evidence

| Atlas field | Canon field | Transform |
|---|---|---|
| `id` (deterministic hash, 12–16 char) | `id` | identity |
| `hypothesis_id` | `claim_id` | identity |
| `evidence_class` (5-value enum) | `evidence_type` (domain-owned string) | enum `.value` |
| `quality` (3-value enum) | `tier` (4-value enum) | lossy — see table below |
| `direction` (3-value enum) | `polarity` (3-value enum) | `inconclusive → neutral`, else identity |
| `summary` (str) | (not mapped; shown in Decision / in artifact body) | |
| `statistics` (dict) | (not mapped; in artifact body) | |
| `data_range` (str) | (not mapped; in artifact body) | |
| `source_hash` (sha256[:16]) | `artifact.content_hash` | replaced by full-file SHA-256 of the evidence JSON for canonical replay |
| `created_at` | `emitted_at`, `observed_at`, `role_declared_at` | identity |

### quality → tier (the lossy map, policy-declared)

This is the mapping encoded in the canon Policy `atlas.evidence_quality_to_canon_tier` v1:

| `quality` | `evidence_class` | `tier` | Reason |
|---|---|---|---|
| `weak` | any | `internal_operational` | in-sample only; pre-external-commitment |
| `moderate` | any | `external_conversation` | significant but single test |
| `strong` | `live_observation` | `external_transaction` | actual market behavior observed |
| `strong` | anything else | `external_commitment` | OOS / multi-test significance — committed to a dataset |

**Caveats.** Atlas's quality is a statistical-rigor axis; canon's tier is a
bindingness-to-external-reality axis. The mapping is philosophically
defensible (OOS evidence is "more external" than in-sample), but it does
not preserve all atlas semantics. A research pass wishing to reason over
atlas's rigor axis should read the original `.atlas/evidence/<id>.json` via
the ArtifactPointer, not rely on the canon `tier` alone.

**If the mapping ever changes** (e.g. future versions extend canon's tier
enum via Policy), the adapter emits an `amend_policy` Decision against
`atlas.evidence_quality_to_canon_tier`, bumping the version. Historical
envelopes retain the version they were emitted under (see
`Policy.provenance`).

## Decision mapping

Atlas's `runner.evaluate_and_decide()` produces `promote | kill | continue |
pivot` outcomes. Canon Decision shape (see `schemas/decision.schema.json`):

- `candidate_claims = [hypothesis.id]` — atlas evaluates one claim per cycle;
  no cross-hypothesis arbitration. `rejected_alternatives` and `arbitration`
  are therefore omitted (schema requires them only when `candidate_claims`
  has >1 entry).
- `chosen_claim_id = hypothesis.id`
- `cited_evidence = [e.id for e in cycle.evidence]`
- `contradictions_addressed` populated for any `polarity=contradicts`
  evidence. Treatment: `hard_gated` when the decision is `kill`,
  `accepted_as_partial_constraint` otherwise.
- `rationale` — atlas's free-form cycle decision narrative.
- `policies_in_force` — always includes `atlas.evidence_quality_to_canon_tier`
  at the version effective at decision time.
- `promotion_id` — required when `kind="promote"`. Atlas's Primitive id
  (when available) is used; otherwise a synthetic id.

## EventLogEntry mapping

Two event_kinds are produced by the atlas adapter:

1. **phase_transition** — on any `HypothesisStatus` change. Claims are
   immutable; status is captured as a phase-transition event with
   `claim_id`, `from_phase`, `to_phase`. Phases: FORMULATED→draft,
   TESTING→probe, {SUPPORTED,FALSIFIED,PROMOTED}→promotion. (Multiple
   transitions into `promotion` are legal and distinguishable by their
   triggering_decision_id.)

2. **methodology_log** — on entry to the probe phase, per canon.md Phase
   Invariants ("Methodology log entry required on entry to probe").
   `artifact` is a canon ArtifactPointer to the atlas `methodology.jsonl`
   entry for that hypothesis. `summary` is optional free-form prose.

Other event_kinds (canon_violation, activation_change, cross_layer_read,
advisory_rejection, trigger_fired) are reserved for future work.

## Things deliberately not mapped

- **Atlas ResearchCycle** — an operational grouping, not a canon object.
  A Decision envelope represents the cycle's outcome; the cycle's signals,
  experiment executions, and intermediate state live in atlas-native storage
  under `.atlas/cycles/` and `sessions/`.
- **Atlas Experiment** — canon has no first-class "Probe" object; the probe
  phase is represented implicitly by the EventLogEntry stream and
  (optionally) in the Claim's `thresholds` field.
- **Atlas Primitive** — canon has `Promotion` (unimplemented in this
  adapter today). A future version of this adapter will emit Promotion
  envelopes when atlas promotes a hypothesis. Until then, promoted
  hypotheses surface as Decision(kind=promote) envelopes with
  `promotion_id` pointing at the atlas primitive record; the Promotion
  envelope is deferred.
- **Atlas causal graph** — domain-specific causal model; canon does not
  currently model graph edges. Graph structure remains in atlas's
  `graph/causal_graph.json`.

## Open questions (surfacing now to avoid silent divergence)

- **Promotion envelope**. Should the adapter emit a canon Promotion envelope
  alongside Decision(kind=promote), per canon.md §Phase invariants?
  Blocker: canon Promotion requires `external_validation` tier satisfied
  and a `ceiling_check`. Atlas's promotion gate is dual-significance +
  OOS, not an external-validation tier. Requires either: a Policy
  declaring atlas's gate AS the external-validation tier for the crypto
  domain, or deferral until canon gains a research-style promotion-gate
  variant. **Deferred; surfaced in ADR-0026 for follow-up.**

- **Bonferroni adjustment**. Atlas applies Bonferroni correction per cycle,
  adjusting each hypothesis's effective alpha. The canon Claim's
  `thresholds.alpha` records the *pre-registered* alpha, not the
  post-correction effective alpha. The correction is captured in the
  Decision's `rationale`. If downstream canon consumers want the adjusted
  alpha mechanically, we may need a `thresholds.effective_alpha` field by
  convention.

- **Phase transitions produced outside the runner** (e.g. manual CLI
  promotion). These are currently invisible to the adapter since the CLI
  writes directly to `.atlas/` without firing an event. Migration script
  synthesizes phase transitions from the hypothesis's current status at
  migration time, but live dual-write mode will need a runner-level hook.
