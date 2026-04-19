"""Canon adapter smoke tests — atlas.adapters.discovery.emit.

Validates that each emit_* function returns a dict matching the expected
shape. Schema-level validation against the L1 discovery-framework schemas
is exercised by `python -m atlas.adapters.discovery.migrate --dry-run`;
these tests are lighter-weight shape checks suitable for the main unit
test suite.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from atlas.adapters.discovery import (
    emit_claim,
    emit_evidence,
    emit_event_log,
    emit_policy_tier_mapping,
)
from atlas.models.evidence import (
    Evidence,
    EvidenceClass,
    EvidenceDirection,
    EvidenceQuality,
)
from atlas.models.hypothesis import Hypothesis


ATLAS_ROOT = Path(__file__).resolve().parent.parent


def _make_hypothesis(**overrides):
    base = dict(
        id="abc123def456abcd",
        claim="BTC reverts post-funding reset",
        rationale="funding pressure unwinds after reset",
        falsification_criteria="short-after-reset returns not significant",
        significance_threshold=0.05,
    )
    base.update(overrides)
    return Hypothesis(**base)


def _make_evidence(**overrides):
    base = dict(
        experiment_id="exp-001",
        hypothesis_id="abc123def456abcd",
        evidence_class=EvidenceClass.BACKTEST_RESULT,
        quality=EvidenceQuality.MODERATE,
        direction=EvidenceDirection.SUPPORTS,
        summary="backtest positive",
    )
    base.update(overrides)
    return Evidence(**base)


def test_claim_core_shape():
    c = emit_claim(_make_hypothesis(), ATLAS_ROOT)
    assert c["id"] == "abc123def456abcd"
    assert c["object_type"] == "Claim"
    assert c["spec_version"] == "0.1.0"
    assert c["statement"] == "BTC reverts post-funding reset"
    # falsification_criteria wrapped from str → [str]
    assert c["falsification_criteria"] == [
        "short-after-reset returns not significant"
    ]
    assert c["thresholds"]["alpha"] == 0.05
    assert c["binding"] == "binding"
    assert c["sources"] == []
    assert c["emitter"] == "L3:atlas"
    assert c["layer"] == "L3"
    assert "Claim" in c["roles"]
    assert c["exposure"]["capital_at_risk"] == 0
    assert c["exposure"]["reversibility"] == "reversible"
    assert c["instance_id"] == "atlas"


def test_claim_emitted_at_matches_created_at():
    h = _make_hypothesis()
    c = emit_claim(h, ATLAS_ROOT)
    # role_declared_at <= emitted_at is a canon.md rule; here they're equal
    assert c["role_declared_at"] == c["emitted_at"]


@pytest.mark.parametrize(
    "quality,evidence_class,expected_tier",
    [
        (EvidenceQuality.WEAK, EvidenceClass.BACKTEST_RESULT, "internal_operational"),
        (EvidenceQuality.MODERATE, EvidenceClass.BACKTEST_RESULT, "external_conversation"),
        (EvidenceQuality.MODERATE, EvidenceClass.OUT_OF_SAMPLE_TEST, "external_conversation"),
        (EvidenceQuality.STRONG, EvidenceClass.OUT_OF_SAMPLE_TEST, "external_commitment"),
        (EvidenceQuality.STRONG, EvidenceClass.BACKTEST_RESULT, "external_commitment"),
        (EvidenceQuality.STRONG, EvidenceClass.LIVE_OBSERVATION, "external_transaction"),
    ],
)
def test_evidence_tier_mapping(quality, evidence_class, expected_tier):
    e = _make_evidence(quality=quality, evidence_class=evidence_class)
    env = emit_evidence(e, ATLAS_ROOT)
    assert env["tier"] == expected_tier


@pytest.mark.parametrize(
    "direction,expected_polarity",
    [
        (EvidenceDirection.SUPPORTS, "supports"),
        (EvidenceDirection.CONTRADICTS, "contradicts"),
        (EvidenceDirection.INCONCLUSIVE, "neutral"),
    ],
)
def test_evidence_polarity_mapping(direction, expected_polarity):
    e = _make_evidence(direction=direction)
    env = emit_evidence(e, ATLAS_ROOT)
    assert env["polarity"] == expected_polarity


def test_evidence_claim_id_preserved():
    e = _make_evidence()
    env = emit_evidence(e, ATLAS_ROOT)
    assert env["claim_id"] == "abc123def456abcd"
    assert env["evidence_type"] == "backtest_result"
    assert env["artifact"]["content_hash"].startswith("sha256:")


def test_event_log_phase_transition_shape():
    now = datetime.now(timezone.utc)
    ev = emit_event_log(
        event_id="pt-abc-draft-probe",
        event_kind="phase_transition",
        emitted_at=now,
        claim_id="abc123def456abcd",
        from_phase="draft",
        to_phase="probe",
    )
    assert ev["object_type"] == "EventLogEntry"
    assert ev["event_kind"] == "phase_transition"
    assert ev["phase_transition"]["claim_id"] == "abc123def456abcd"
    assert ev["phase_transition"]["from_phase"] == "draft"
    assert ev["phase_transition"]["to_phase"] == "probe"
    assert ev["subject_id"] == "abc123def456abcd"


def test_event_log_rejects_unsupported_kinds():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="adapter does not emit"):
        emit_event_log(
            event_id="x", event_kind="trigger_fired", emitted_at=now,
        )


def test_policy_tier_mapping_shape():
    p = emit_policy_tier_mapping()
    assert p["object_type"] == "Policy"
    assert p["class"] == "operational"
    assert p["scope"] == "L3:atlas"
    assert p["field_path"] == "evidence.tier_mapping"
    assert p["version"] == "1"
    assert p["issuer"] == "L3:atlas"
    # Policy schema has additionalProperties:false and does NOT include instance_id
    assert "instance_id" not in p
    # Sanity: rules cover all 4 input enum states
    rules = p["value"]["rules"]
    assert len(rules) == 4
    assert {r["then_tier"] for r in rules} == {
        "internal_operational",
        "external_conversation",
        "external_commitment",
        "external_transaction",
    }


def test_policy_has_valid_provenance_chain():
    p = emit_policy_tier_mapping()
    assert len(p["provenance"]) == 1
    assert p["provenance"][0]["version"] == p["version"]
    # rollback_rule precedence MUST be a permutation of rules[*].id (canon.md rule 4)
    rule_ids = [r["id"] for r in p["rollback_rule"]["rules"]]
    assert sorted(p["rollback_rule"]["precedence"]) == sorted(rule_ids)
