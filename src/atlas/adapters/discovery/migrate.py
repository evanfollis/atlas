"""One-shot backfill: atlas .atlas/* → canon .canon/*.

Usage:
    python -m atlas.adapters.discovery.migrate --atlas /opt/workspace/projects/atlas [--dry-run]

Reads all atlas hypotheses + evidence, emits canon envelopes via emit.py,
validates each against the JSON Schemas at
/opt/workspace/projects/context-repository/spec/discovery-framework/schemas/,
and writes to .canon/ (unless --dry-run, which validates but does not write).

Phase-transition EventLogEntry records are synthesized from each
Hypothesis's current status.

The one-time tier Policy is written first (at .canon/policies/<id>.json)
since every Decision envelope cites it.

Exit codes:
    0 — all envelopes emitted and validated
    1 — some envelopes failed validation (details on stderr)
    2 — adapter or schema loading failure
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from atlas.adapters.discovery.emit import (
    EMITTER,
    INSTANCE_ID,
    PHASE_FOR_STATUS,
    TIER_POLICY_ID,
    _iso,
    _sha256_bytes,
    canon_dir,
    emit_claim,
    emit_event_log,
    emit_evidence,
    emit_policy_tier_mapping,
)
from atlas.models.evidence import Evidence
from atlas.models.hypothesis import Hypothesis, HypothesisStatus


DEFAULT_SCHEMA_DIR = Path(
    "/opt/workspace/projects/context-repository/spec/discovery-framework/schemas"
)


def _load_schema_registry(schema_dir: Path):
    """Load every *.schema.json and build a jsonschema Registry for $ref resolution."""
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except Exception as exc:  # pragma: no cover
        print(
            f"FATAL: jsonschema + referencing required but missing: {exc}",
            file=sys.stderr,
        )
        print(
            "install via: .venv/bin/pip install 'jsonschema>=4.20' 'referencing>=0.30'",
            file=sys.stderr,
        )
        raise

    resources: list[tuple[str, Resource]] = []
    schemas: dict[str, dict] = {}
    for p in sorted(schema_dir.glob("*.schema.json")):
        with open(p) as f:
            body = json.load(f)
        sid = body["$id"]
        schemas[p.name] = body
        resources.append((sid, Resource.from_contents(body)))

    # Register schemas under both their full $id AND the bare filename they
    # are $ref'd by (e.g. "common.schema.json"). Without the bare alias the
    # relative $refs in claim.schema.json, etc., cannot be resolved by the
    # referencing registry when a draft-2020-12 validator walks the tree.
    extra: list[tuple[str, Resource]] = []
    for fname, body in schemas.items():
        extra.append((fname, Resource.from_contents(body)))

    registry = Registry().with_resources(resources + extra)
    validators = {
        body["title"]: Draft202012Validator(body, registry=registry)
        for _, body in schemas.items()
        if "title" in body
    }
    return validators


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _validate(envelope: dict, validators: dict, object_type: str) -> list[str]:
    v = validators.get(object_type)
    if not v:
        return [f"no validator for object_type={object_type!r}"]
    errors = sorted(v.iter_errors(envelope), key=lambda e: e.path)
    return [
        f"{'/'.join(str(p) for p in err.absolute_path)}: {err.message}"
        for err in errors
    ]


def _write_envelope(envelope: dict, dest: Path, dry_run: bool) -> None:
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(envelope, f, indent=2, sort_keys=True)
    tmp.replace(dest)


def migrate(atlas_root: Path, schema_dir: Path, dry_run: bool) -> int:
    atlas_root = Path(atlas_root)
    if not (atlas_root / ".atlas").is_dir():
        print(f"no .atlas/ under {atlas_root}", file=sys.stderr)
        return 2

    canon_root = canon_dir(atlas_root)
    validators = _load_schema_registry(schema_dir)

    hyp_ok = hyp_bad = 0
    ev_ok = ev_bad = 0
    event_ok = event_bad = 0
    pol_ok = pol_bad = 0

    # 1) Tier-mapping policy first (referenced by every Decision)
    pol = emit_policy_tier_mapping()
    errs = _validate(pol, validators, "Policy")
    if errs:
        pol_bad += 1
        print(f"[POLICY] {TIER_POLICY_ID}: {errs}", file=sys.stderr)
    else:
        pol_ok += 1
        _write_envelope(pol, canon_root / "policies" / f"{TIER_POLICY_ID}.json", dry_run)

    # 2) Claims
    hyp_dir = atlas_root / ".atlas" / "hypotheses"
    for p in sorted(hyp_dir.glob("*.json")):
        try:
            h = Hypothesis.model_validate(_load_json(p))
        except Exception as exc:
            hyp_bad += 1
            print(f"[PARSE] hypothesis {p.name}: {exc}", file=sys.stderr)
            continue
        claim_env = emit_claim(h, atlas_root)
        errs = _validate(claim_env, validators, "Claim")
        if errs:
            hyp_bad += 1
            print(f"[CLAIM] {h.id}: {errs}", file=sys.stderr)
            continue
        hyp_ok += 1
        _write_envelope(
            claim_env, canon_root / "claims" / f"{h.id}.json", dry_run,
        )

        # Synthesize phase-transition events from current status.
        # Every hypothesis had to pass through draft on the way to current
        # state, so we emit the transitions in order. We emit at most two
        # events (draft→probe, probe→promotion) and use the hypothesis's
        # created_at as emitted_at; it's the best timestamp available
        # historically.
        target_phase = PHASE_FOR_STATUS[h.status]
        ordered_phases = ["draft", "probe", "promotion"]
        current_idx = ordered_phases.index(target_phase)
        prev_phase = "draft"
        for i in range(1, current_idx + 1):
            to_phase = ordered_phases[i]
            ev_id = f"pt-{h.id}-{prev_phase}-{to_phase}"
            try:
                event = emit_event_log(
                    event_id=ev_id,
                    event_kind="phase_transition",
                    emitted_at=h.created_at,
                    claim_id=h.id,
                    from_phase=prev_phase,
                    to_phase=to_phase,
                )
            except Exception as exc:
                event_bad += 1
                print(f"[EVENT] {ev_id}: {exc}", file=sys.stderr)
                continue
            errs = _validate(event, validators, "EventLogEntry")
            if errs:
                event_bad += 1
                print(f"[EVENT] {ev_id}: {errs}", file=sys.stderr)
                continue
            event_ok += 1
            _write_envelope(
                event, canon_root / "event_log" / f"{ev_id}.json", dry_run,
            )
            prev_phase = to_phase

    # 3) Evidence
    ev_dir = atlas_root / ".atlas" / "evidence"
    for p in sorted(ev_dir.glob("*.json")):
        try:
            e = Evidence.model_validate(_load_json(p))
        except Exception as exc:
            ev_bad += 1
            print(f"[PARSE] evidence {p.name}: {exc}", file=sys.stderr)
            continue
        ev_env = emit_evidence(e, atlas_root)
        errs = _validate(ev_env, validators, "Evidence")
        if errs:
            ev_bad += 1
            print(f"[EVIDENCE] {e.id}: {errs}", file=sys.stderr)
            continue
        ev_ok += 1
        _write_envelope(
            ev_env, canon_root / "evidence" / f"{e.id}.json", dry_run,
        )

    total_bad = hyp_bad + ev_bad + event_bad + pol_bad
    mode = "dry-run" if dry_run else "write"
    print(
        f"[{mode}] "
        f"claims: {hyp_ok} ok / {hyp_bad} bad, "
        f"evidence: {ev_ok} ok / {ev_bad} bad, "
        f"events: {event_ok} ok / {event_bad} bad, "
        f"policies: {pol_ok} ok / {pol_bad} bad"
    )
    return 0 if total_bad == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--atlas", type=Path, default=Path.cwd(),
                    help="atlas repo root (default: cwd)")
    ap.add_argument("--schemas", type=Path, default=DEFAULT_SCHEMA_DIR,
                    help=f"schema dir (default: {DEFAULT_SCHEMA_DIR})")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate only; do not write .canon/")
    args = ap.parse_args()

    try:
        return migrate(args.atlas, args.schemas, args.dry_run)
    except Exception:
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
