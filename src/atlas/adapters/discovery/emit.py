"""Emit canon envelopes from atlas Pydantic records.

Each emit_* function returns a dict conforming to its respective JSON Schema
in /opt/workspace/projects/context-repository/spec/discovery-framework/schemas/.
No I/O here — the caller is responsible for writing the dict to .canon/ and
running the validator.

Conventions:
- `emitter`  = "L3:atlas"  — atlas operates at the domain-layer (L3).
- `layer`    = "L3".
- `binding`  = "binding" for domain research claims (NOT meta-layer outputs).
- `sources`  = []          — atlas does not currently cite upstream canon.
                              Left empty (valid per schema) so the
                              influence-firewall check is trivially satisfied.

The `tier` mapping from atlas's 3-tier EvidenceQuality to canon's 4-tier
enum is documented in MAPPING.md in this directory AND expressed as a canon
Policy via emit_policy_tier_mapping(). Future sessions reading canon
envelopes see the mapping in Policy.provenance.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from atlas.models.evidence import Evidence, EvidenceDirection, EvidenceQuality
from atlas.models.hypothesis import Hypothesis, HypothesisStatus


SPEC_VERSION = "0.1.0"
EMITTER = "L3:atlas"
LAYER = "L3"
INSTANCE_ID = "atlas"

TIER_POLICY_ID = "atlas.evidence_quality_to_canon_tier"
TIER_POLICY_VERSION = "1"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def canon_dir(atlas_path: Path) -> Path:
    """Return the .canon/ directory under an atlas root, creating if missing."""
    d = Path(atlas_path) / ".canon"
    d.mkdir(parents=True, exist_ok=True)
    for sub in ("claims", "evidence", "decisions", "event_log", "policies"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def _iso(dt: datetime | str) -> str:
    """Convert datetime or isoformat-ish string to canon Timestamp (RFC 3339)."""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _default_exposure() -> dict[str, Any]:
    """Minimal exposure envelope for atlas research records.

    Atlas research commits no capital and its outputs are internal to the
    research loop until a promoted Primitive is fed downstream. Every field
    is required by the canon Exposure schema.
    """
    return {
        "capital_at_risk": 0,
        "reversibility": "reversible",
        "correlation_tags": [],
        "time_to_realization": "P0D",
        "blast_radius": "local",
    }


def _quality_to_tier(quality: EvidenceQuality, evidence_class: str) -> str:
    """Lossy mapping from atlas.Evidence.quality to canon.Evidence.tier.

    Atlas's quality measures statistical rigor (weak/moderate/strong). Canon's
    tier measures bindingness to external reality
    (internal_operational / external_conversation / external_commitment /
    external_transaction). These axes are not identical; the mapping is
    documented in MAPPING.md and codified as a Policy (see
    emit_policy_tier_mapping).

    Rule: STRONG evidence that came from live_observation is
    external_transaction (actual market behavior). STRONG from OOS backtest is
    external_commitment (committed to a real dataset, not in-sample cherry-
    picking). MODERATE is external_conversation (moderate support, one test).
    WEAK is internal_operational (in-sample only, pre-commitment).
    """
    if quality == EvidenceQuality.WEAK:
        return "internal_operational"
    if quality == EvidenceQuality.MODERATE:
        return "external_conversation"
    # STRONG
    if evidence_class == "live_observation":
        return "external_transaction"
    return "external_commitment"


def _direction_to_polarity(direction: EvidenceDirection) -> str:
    return {
        EvidenceDirection.SUPPORTS: "supports",
        EvidenceDirection.CONTRADICTS: "contradicts",
        EvidenceDirection.INCONCLUSIVE: "neutral",
    }[direction]


def _artifact_pointer(
    uri: str, content_hash: str, version: str, anchor: str | None = None,
    media_type: str | None = None,
) -> dict[str, Any]:
    ap: dict[str, Any] = {
        "uri": uri,
        "content_hash": content_hash,
        "version": version,
    }
    if anchor:
        ap["anchor"] = anchor
    if media_type:
        ap["media_type"] = media_type
    return ap


def _common_envelope(object_type: str, id_: str, emitted_at: str,
                     role_declared_at: str | None = None,
                     binding: str = "binding") -> dict[str, Any]:
    """Shared envelope fields for all canon object types."""
    return {
        "id": id_,
        "spec_version": SPEC_VERSION,
        "object_type": object_type,
        "emitted_at": emitted_at,
        "emitter": EMITTER,
        "layer": LAYER,
        "roles": [object_type],
        "role_declared_at": role_declared_at or emitted_at,
        "binding": binding,
        "sources": [],
        "instance_id": INSTANCE_ID,
    }


# --------------------------------------------------------------------------
# Claim
# --------------------------------------------------------------------------


def emit_claim(h: Hypothesis, atlas_path: Path | str) -> dict[str, Any]:
    """Atlas Hypothesis → canon Claim envelope.

    Mapping:
      - Claim.id                     = Hypothesis.id (already sha256[:16] of canonical claim)
      - Claim.statement              = Hypothesis.claim (immutable per canon)
      - Claim.falsification_criteria = [Hypothesis.falsification_criteria]   (wrap str in list)
      - Claim.thresholds             = {"alpha": Hypothesis.significance_threshold, ...}
      - Claim.emitted_at             = Hypothesis.created_at (ISO 8601)
      - Claim.artifact               = ArtifactPointer to the atlas hypothesis JSON file

    The Hypothesis.status is NOT written into the Claim envelope (Claims are
    immutable; status transitions are recorded as EventLogEntry(phase_transition)
    events — see emit_event_log).
    """
    atlas_path = Path(atlas_path)
    created = _iso(h.created_at)
    envelope = _common_envelope("Claim", h.id, created, binding="binding")
    envelope["statement"] = h.claim
    envelope["falsification_criteria"] = [h.falsification_criteria]
    envelope["thresholds"] = {
        "alpha": h.significance_threshold,
    }
    envelope["exposure"] = _default_exposure()

    # Point at the on-disk atlas hypothesis JSON if it exists, with content hash.
    hyp_json = atlas_path / ".atlas" / "hypotheses" / f"{h.id}.json"
    if hyp_json.exists():
        envelope["artifact"] = _artifact_pointer(
            uri=f"file://{hyp_json}",
            content_hash=_sha256_file(hyp_json),
            version=str(int(hyp_json.stat().st_mtime)),
            media_type="application/json",
        )
    return envelope


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


def emit_evidence(e: Evidence, atlas_path: Path | str) -> dict[str, Any]:
    """Atlas Evidence → canon Evidence envelope.

    Mapping:
      - Evidence.id              = Evidence.id                        (atlas deterministic)
      - Evidence.claim_id        = Evidence.hypothesis_id
      - Evidence.evidence_type   = Evidence.evidence_class.value      (domain-owned free-form string)
      - Evidence.tier            = _quality_to_tier(...)              (Policy-documented lossy map)
      - Evidence.polarity        = _direction_to_polarity(direction)  (inconclusive → neutral)
      - Evidence.artifact        = ArtifactPointer to the atlas evidence JSON
      - Evidence.observed_at     = Evidence.created_at
    """
    atlas_path = Path(atlas_path)
    created = _iso(e.created_at)
    envelope = _common_envelope(
        "Evidence", e.id, created, binding="binding",
    )
    # Evidence schema REQUIRES binding + sources + claim_id + evidence_type +
    # tier + polarity + artifact (beyond EnvelopeBase).
    envelope["claim_id"] = e.hypothesis_id
    envelope["evidence_type"] = e.evidence_class.value
    envelope["tier"] = _quality_to_tier(e.quality, e.evidence_class.value)
    envelope["polarity"] = _direction_to_polarity(e.direction)
    envelope["observed_at"] = created

    ev_json = atlas_path / ".atlas" / "evidence" / f"{e.id}.json"
    if ev_json.exists():
        envelope["artifact"] = _artifact_pointer(
            uri=f"file://{ev_json}",
            content_hash=_sha256_file(ev_json),
            version=str(int(ev_json.stat().st_mtime)),
            media_type="application/json",
        )
    else:
        # Fallback: synthesize an artifact pointer from the evidence summary
        # hash. The Evidence schema REQUIRES artifact, so this path keeps the
        # envelope valid even when the source JSON is missing (rare).
        payload = json.dumps(
            {"summary": e.summary, "statistics": e.statistics,
             "data_range": e.data_range},
            sort_keys=True,
        ).encode("utf-8")
        envelope["artifact"] = _artifact_pointer(
            uri=f"atlas-evidence:{e.id}",
            content_hash=_sha256_bytes(payload),
            version=created,
        )
    return envelope


# --------------------------------------------------------------------------
# Decision
# --------------------------------------------------------------------------


def emit_decision(
    *,
    decision_id: str,
    kind: str,
    hypothesis: Hypothesis,
    evidence: Iterable[Evidence],
    rationale: str,
    emitted_at: str | datetime | None = None,
    atlas_path: Path | str,
    promotion_id: str | None = None,
) -> dict[str, Any]:
    """Emit a canon Decision for an atlas cycle outcome.

    Atlas currently produces promote|kill|continue|pivot decisions at the
    runner level. This function expects a caller (migrate.py or atlas's
    runner in dual-write mode) to pass in the decision kind, the target
    hypothesis, and the relevant evidence set.

    Contention-integrity rules:
    - candidate_claims == [hypothesis.id] (atlas evaluates one claim at a time;
      no cross-hypothesis arbitration today)
    - rejected_alternatives omitted (candidate_claims has 1 entry)
    - arbitration omitted for the same reason

    If kind=promote, a promotion_id MUST be provided.
    """
    if kind == "promote" and not promotion_id:
        raise ValueError("promotion_id required when kind='promote'")
    if kind not in {"promote", "kill", "continue", "pivot"}:
        raise ValueError(f"atlas does not emit Decision.kind={kind!r}")

    dt = emitted_at or datetime.now(timezone.utc)
    emitted = _iso(dt) if not isinstance(dt, str) else dt

    envelope = _common_envelope("Decision", decision_id, emitted, binding="binding")
    envelope["kind"] = kind
    envelope["candidate_claims"] = [hypothesis.id]
    envelope["chosen_claim_id"] = hypothesis.id
    envelope["cited_evidence"] = [e.id for e in evidence]

    # contradictory evidence MUST be cited at decision time
    contradictions = [e for e in evidence if e.direction == EvidenceDirection.CONTRADICTS]
    if contradictions:
        envelope["contradictions_addressed"] = [
            {
                "evidence_id": c.id,
                "treatment": (
                    "hard_gated" if kind == "kill" else "accepted_as_partial_constraint"
                ),
                "rationale": c.summary,
            }
            for c in contradictions
        ]

    envelope["rationale"] = rationale
    envelope["policies_in_force"] = [
        {
            "policy_id": TIER_POLICY_ID,
            "version": TIER_POLICY_VERSION,
            "class": "operational",
        }
    ]
    envelope["exposure"] = _default_exposure()

    if promotion_id:
        envelope["promotion_id"] = promotion_id
    return envelope


# --------------------------------------------------------------------------
# EventLogEntry (phase transitions + methodology logs)
# --------------------------------------------------------------------------


PHASE_FOR_STATUS = {
    HypothesisStatus.FORMULATED: "draft",
    HypothesisStatus.TESTING: "probe",
    HypothesisStatus.SUPPORTED: "promotion",
    HypothesisStatus.FALSIFIED: "promotion",
    HypothesisStatus.PROMOTED: "promotion",
}


def emit_event_log(
    *,
    event_id: str,
    event_kind: str,
    emitted_at: str | datetime,
    claim_id: str | None = None,
    from_phase: str | None = None,
    to_phase: str | None = None,
    triggering_decision_id: str | None = None,
    methodology_artifact: dict[str, Any] | None = None,
    methodology_summary: str | None = None,
) -> dict[str, Any]:
    """Emit a canon EventLogEntry.

    Only two event_kinds are produced by the atlas adapter today:

      - phase_transition: claim_id FORMULATED→TESTING, TESTING→PROMOTION, etc.
      - methodology_log: a pointer to an atlas methodology record
                        (artifact is a canon ArtifactPointer)

    Other event_kinds (canon_violation, activation_change, cross_layer_read,
    advisory_rejection, trigger_fired) are reserved for future work; this
    adapter does not emit them.
    """
    if event_kind not in {"phase_transition", "methodology_log"}:
        raise ValueError(
            f"atlas adapter does not emit EventLogEntry.event_kind={event_kind!r}"
        )

    emitted = _iso(emitted_at) if not isinstance(emitted_at, str) else emitted_at
    envelope = _common_envelope(
        "EventLogEntry", event_id, emitted, binding="binding",
    )
    envelope["event_kind"] = event_kind

    if event_kind == "phase_transition":
        if not (claim_id and from_phase and to_phase):
            raise ValueError("phase_transition requires claim_id, from_phase, to_phase")
        pt: dict[str, Any] = {
            "claim_id": claim_id,
            "from_phase": from_phase,
            "to_phase": to_phase,
        }
        if triggering_decision_id:
            pt["triggering_decision_id"] = triggering_decision_id
        envelope["phase_transition"] = pt
        envelope["subject_id"] = claim_id
    elif event_kind == "methodology_log":
        if not methodology_artifact:
            raise ValueError("methodology_log requires methodology_artifact")
        ml: dict[str, Any] = {"artifact": methodology_artifact}
        if methodology_summary:
            ml["summary"] = methodology_summary
        envelope["methodology_log"] = ml
    return envelope


# --------------------------------------------------------------------------
# Policy — the tier mapping
# --------------------------------------------------------------------------


def emit_policy_tier_mapping(effective_from: str | datetime | None = None) -> dict[str, Any]:
    """One-shot canon Policy declaring the quality→tier mapping for atlas.

    Written once at migration time. Referenced by every Decision's
    policies_in_force. Future updates go through the Policy amendment path
    (Decision.kind=amend_policy).
    """
    ts = effective_from or datetime.now(timezone.utc)
    emitted = _iso(ts) if not isinstance(ts, str) else ts

    envelope = _common_envelope(
        "Policy", TIER_POLICY_ID, emitted, binding="binding",
    )
    # Policy schema has additionalProperties:false and does not list
    # instance_id; remove it so the envelope validates.
    envelope.pop("instance_id", None)
    envelope["class"] = "operational"
    envelope["scope"] = f"L3:{INSTANCE_ID}"
    envelope["field_path"] = "evidence.tier_mapping"
    envelope["value"] = {
        "source_enum": "atlas.EvidenceQuality",
        "target_enum": "canon.tier",
        "rules": [
            {"when": {"quality": "weak"},
             "then_tier": "internal_operational",
             "rationale": "in-sample only, pre-external-commitment"},
            {"when": {"quality": "moderate"},
             "then_tier": "external_conversation",
             "rationale": "significant but single test"},
            {"when": {"quality": "strong", "evidence_class_not": "live_observation"},
             "then_tier": "external_commitment",
             "rationale": "OOS / multi-test significance — committed to dataset"},
            {"when": {"quality": "strong", "evidence_class": "live_observation"},
             "then_tier": "external_transaction",
             "rationale": "actual market behavior observed"},
        ],
    }
    envelope["version"] = TIER_POLICY_VERSION
    envelope["issuer"] = EMITTER
    envelope["amendment_authority"] = [EMITTER, "human:evan"]
    envelope["ratification_rule"] = {
        "kind": "principal_signoff",
        "signatories": ["human:evan"],
    }
    envelope["rollback_rule"] = {
        "rules": [
            {
                "id": "spec_version_bump",
                "condition": (
                    "canon.spec_version has advanced beyond this Policy's "
                    "spec_version and the target_enum has changed"
                ),
                "restore_version": "previous",
            },
        ],
        "precedence": ["spec_version_bump"],
    }
    envelope["provenance"] = [
        {
            "version": TIER_POLICY_VERSION,
            "effective_from": emitted,
        }
    ]
    envelope["effective_from"] = emitted
    envelope["effective_until"] = None
    return envelope
