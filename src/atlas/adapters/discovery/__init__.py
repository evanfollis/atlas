"""Canon adapter — emits discovery-framework canon envelopes from atlas state.

The atlas research loop (src/atlas/) persists its own Pydantic state in .atlas/
JSON files. This adapter maps each atlas record to a canon envelope conforming
to the L1 spec at /opt/workspace/projects/context-repository/spec/discovery-
framework/ (v0.1.0), producing a parallel .canon/ store that atlas's behavior
does not otherwise depend on.

The adapter is additive — it does NOT modify atlas's existing write path.
The migrate.py entry point backfills historical records; the emit.py
functions can be called in dual-write mode once atlas's runner is wired to
call them alongside StateStore.save().

Public API:
    emit_claim(h, atlas_path)           -> canon Claim dict
    emit_evidence(e, atlas_path)        -> canon Evidence dict
    emit_decision(cycle, ..., atlas_path) -> canon Decision dict
    emit_event_log(event, atlas_path)   -> canon EventLogEntry dict
    emit_policy_tier_mapping()          -> canon Policy dict for the quality→tier map
    canon_dir(atlas_path)               -> Path to the .canon/ store
"""

from .emit import (
    emit_claim,
    emit_evidence,
    emit_decision,
    emit_event_log,
    emit_policy_tier_mapping,
    canon_dir,
    SPEC_VERSION,
    EMITTER,
    LAYER,
    INSTANCE_ID,
    TIER_POLICY_ID,
    TIER_POLICY_VERSION,
)

__all__ = [
    "emit_claim",
    "emit_evidence",
    "emit_decision",
    "emit_event_log",
    "emit_policy_tier_mapping",
    "canon_dir",
    "SPEC_VERSION",
    "EMITTER",
    "LAYER",
    "INSTANCE_ID",
    "TIER_POLICY_ID",
    "TIER_POLICY_VERSION",
]
