"""Migrate hypothesis IDs to canonical claim hashing.

Previous: sha256(claim.strip())[:16]
New:      sha256(claim_canonical(claim))[:16]

claim_canonical applies: lower, whitespace-collapse, strip trailing punctuation.
This re-keys all hypothesis files and re-links experiments and evidence.

Safe to run multiple times — skips hypotheses whose ID already matches canonical form.

Two-phase commit (write-then-delete) is used to make the migration crash-safe.
Old hypothesis files are NOT deleted until experiments and evidence have been
fully re-linked. A crash mid-migration leaves both old and new hypothesis
files on disk, all experiment/evidence references either intact (if the
re-link phase did not start) or pointing at the new IDs (if it completed).
A re-run picks up where the previous run left off and finishes cleanly.

Merge handling is opt-in via --allow-merge. When two hypotheses share a
canonical hash, only their `claim` text is preserved (in `claim_variants`);
all other fields on the discarded record (rationale, falsification_criteria,
tags, status, etc.) are dropped. Without --allow-merge the script refuses
to run if any merge groups are detected and prints an audit of which fields
diverge between the records that would be collapsed.
"""
import argparse
import json
import sys
from pathlib import Path

# Add src to path so we can import atlas.utils
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from atlas.utils import claim_hash  # noqa: E402


# Audit constant: fields where divergence between merged records would be
# silently lost. Listed for explicit visibility.
HYPOTHESIS_FIELDS_AT_RISK = (
    "rationale",
    "falsification_criteria",
    "significance_threshold",
    "domain",
    "tags",
    "status",
    "parent_primitive_id",
)


def _audit_merge_divergence(entries: list[dict]) -> dict[str, list]:
    """For a merge group, report which at-risk fields differ across records.

    Returns {field_name: [(old_id, value), ...]} for any field whose value
    is not identical across all merge candidates. The caller prints the
    result so the operator sees exactly what would be silently dropped
    before opting into --allow-merge.
    """
    diverging: dict[str, list] = {}
    if len(entries) < 2:
        return diverging
    loaded = [(e["old_id"], json.loads(e["file"].read_text())) for e in entries]
    for field in HYPOTHESIS_FIELDS_AT_RISK:
        values = [(oid, data.get(field)) for oid, data in loaded]
        unique = {repr(v) for _, v in values}
        if len(unique) > 1:
            diverging[field] = values
    return diverging


def run_migration(
    hyp_dir: Path,
    exp_dir: Path,
    evi_dir: Path,
    meta_path: Path,
    *,
    verbose: bool = True,
    allow_merge: bool = False,
) -> dict[str, int]:
    """Migrate hypothesis IDs to canonical hash form, two-phase-commit safe.

    Order of operations:
      Phase 1  — read all hypothesis files; build old_id → new_id mapping.
      Phase 2W — for merge groups, write the merged primary to its new path
                 (does NOT unlink the source files yet).
      Phase 3W — for non-merge renames, write the new-id file (does NOT
                 unlink the old-id file yet).
      Phase 4  — re-link experiments to new hypothesis ids. At this point
                 the new-id files all exist, so experiments cannot be
                 orphaned by the re-link.
      Phase 5  — re-link evidence to new hypothesis ids.
      Phase D  — only after Phases 4–5 complete, delete the old-id source
                 files. A crash before Phase D leaves both copies on disk;
                 the re-link is safe because every experiment/evidence
                 hypothesis_id either equals the old id (target intact) or
                 the new id (target intact).
      Phase 6  — write schema_version marker.
      Phase 7  — integrity check (orphan references).

    Returns a counts dict for assertions / reporting.
    """
    p = print if verbose else (lambda *_a, **_k: None)

    if not hyp_dir.exists():
        p("No hypotheses/ directory found. Nothing to migrate.")
        return {"hypotheses_migrated": 0, "experiments_relinked": 0, "evidence_relinked": 0}

    # Phase 1: Build old_id → new_id mapping
    mapping: dict[str, str] = {}
    merges: dict[str, list[dict]] = {}  # new_id → list of old records that map to it

    for f in sorted(hyp_dir.glob("*.json")):
        data = json.loads(f.read_text())
        old_id = data["id"]
        new_id = claim_hash(data["claim"])
        if old_id == new_id:
            continue  # already canonical
        mapping[old_id] = new_id
        merges.setdefault(new_id, []).append({"old_id": old_id, "claim": data["claim"], "file": f})

    p(f"Hypotheses to migrate: {len(mapping)}")

    # Files queued for deletion in Phase D. We keep them on disk until
    # Phases 4 and 5 are done so a mid-run crash never leaves dangling refs.
    deferred_unlinks: list[Path] = []
    merge_groups = {k: v for k, v in merges.items() if len(v) > 1}

    # Phase 2W: handle merge groups by writing the merged primary file.
    # Do NOT unlink any source file here.
    if merge_groups:
        p(f"\n{len(merge_groups)} merge group(s) detected:")
        for new_id, entries in merge_groups.items():
            p(f"  → {new_id}:")
            for e in entries:
                p(f"    {e['old_id']} | {e['claim'][:80]}")

        # --allow-merge gate: the merge consolidation drops every non-claim
        # field from the discarded records. Refuse to run without explicit
        # opt-in, and print an audit of which fields would diverge so the
        # operator sees exactly what would be lost before re-invoking with
        # --allow-merge.
        if not allow_merge:
            print("\nERROR: merge groups detected but --allow-merge not set.",
                  file=sys.stderr)
            print("Merging silently drops all non-claim fields from discarded "
                  "records (rationale, falsification_criteria, status, etc.).",
                  file=sys.stderr)
            print("Audit of fields that would diverge:", file=sys.stderr)
            for new_id, entries in merge_groups.items():
                divergence = _audit_merge_divergence(entries)
                if not divergence:
                    print(f"  {new_id}: all at-risk fields identical "
                          "(merge would still consolidate to the first "
                          "sorted record).", file=sys.stderr)
                    continue
                print(f"  {new_id}: {len(divergence)} field(s) diverge:",
                      file=sys.stderr)
                for field, values in divergence.items():
                    print(f"    {field}:", file=sys.stderr)
                    for old_id, value in values:
                        print(f"      {old_id}: {value!r}", file=sys.stderr)
            print("\nRe-run with --allow-merge to opt in to the destructive "
                  "consolidation, or merge by hand first.", file=sys.stderr)
            raise SystemExit(2)

        for new_id, entries in merge_groups.items():
            primary = entries[0]
            primary_data = json.loads(primary["file"].read_text())
            variants = primary_data.get("claim_variants", [])
            for other in entries[1:]:
                other_data = json.loads(other["file"].read_text())
                variants.append(other_data["claim"])
                deferred_unlinks.append(other["file"])
                p(f"  Will merge {other['old_id']} into {primary['old_id']} → {new_id}")
            if variants:
                primary_data["claim_variants"] = variants
            primary_data["id"] = new_id
            new_path = hyp_dir / f"{new_id}.json"
            new_path.write_text(json.dumps(primary_data, indent=2, default=str))
            if primary["file"].name != f"{new_id}.json":
                deferred_unlinks.append(primary["file"])
    else:
        p("No merges needed — all canonical hashes are unique.")

    # Phase 3W: rename non-merge hypotheses by writing the new-id file.
    # Do NOT unlink the old-id file here.
    for old_id, new_id in mapping.items():
        if new_id in merge_groups:
            continue  # already handled by the merge writer
        old_path = hyp_dir / f"{old_id}.json"
        new_path = hyp_dir / f"{new_id}.json"
        if not old_path.exists():
            continue
        data = json.loads(old_path.read_text())
        data["id"] = new_id
        new_path.write_text(json.dumps(data, indent=2, default=str))
        deferred_unlinks.append(old_path)
        p(f"  Wrote new hypothesis: {old_id} → {new_id}")

    # Phase 4: re-link experiments. Both the old-id and new-id hypothesis
    # files exist on disk at this point, so a crash mid-loop leaves us in a
    # safe state — every experiment.hypothesis_id (either flavor) still
    # points at an existing target.
    updated_experiments = 0
    for f in sorted(exp_dir.glob("*.json")) if exp_dir.exists() else []:
        data = json.loads(f.read_text())
        changed = False
        for field in ("hypothesis_id", "hyp_id"):
            if data.get(field) in mapping:
                data[field] = mapping[data[field]]
                changed = True
        if changed:
            f.write_text(json.dumps(data, indent=2, default=str))
            updated_experiments += 1
    p(f"Experiment records updated: {updated_experiments}")

    # Phase 5: re-link evidence. Same crash-safety argument as Phase 4.
    updated_evidence = 0
    for f in sorted(evi_dir.glob("*.json")) if evi_dir.exists() else []:
        data = json.loads(f.read_text())
        if data.get("hypothesis_id") in mapping:
            data["hypothesis_id"] = mapping[data["hypothesis_id"]]
            f.write_text(json.dumps(data, indent=2, default=str))
            updated_evidence += 1
    p(f"Evidence records updated: {updated_evidence}")

    # Phase D: now that re-links are complete, drop the deferred old files.
    # Crashing in the middle of this loop is benign — the leftover old-id
    # files are unreferenced by any experiment/evidence and a re-run picks
    # them up via Phase 1 again.
    for path in deferred_unlinks:
        if path.exists():
            path.unlink()

    # Phase 6: schema-version marker.
    version_data = {
        "schema_version": 2,
        "note": "v2: canonical claim hashing (lower+ws-collapse+strip-punct)",
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(version_data, indent=2))
    p(f"Schema version written: {meta_path}")

    # Phase 7: integrity check (orphan references).
    final_hyps = list(hyp_dir.glob("*.json"))
    final_exps = list(exp_dir.glob("*.json")) if exp_dir.exists() else []
    final_evis = list(evi_dir.glob("*.json")) if evi_dir.exists() else []
    p(f"\nFinal counts: {len(final_hyps)} hypotheses, "
      f"{len(final_exps)} experiments, {len(final_evis)} evidence")

    hyp_ids = {json.loads(f.read_text())["id"] for f in final_hyps}
    orphan_exps: list[tuple[str, str]] = []
    for f in final_exps:
        d = json.loads(f.read_text())
        ref = d.get("hypothesis_id") or d.get("hyp_id")
        if ref and ref not in hyp_ids:
            orphan_exps.append((f.stem, ref))

    orphan_evis: list[tuple[str, str]] = []
    for f in final_evis:
        d = json.loads(f.read_text())
        ref = d.get("hypothesis_id")
        if ref and ref not in hyp_ids:
            orphan_evis.append((f.stem, ref))

    if orphan_exps:
        p(f"\nWARNING: {len(orphan_exps)} orphan experiment(s): {orphan_exps}")
    if orphan_evis:
        p(f"\nWARNING: {len(orphan_evis)} orphan evidence record(s): {orphan_evis}")

    return {
        "hypotheses_migrated": len(mapping),
        "experiments_relinked": updated_experiments,
        "evidence_relinked": updated_evidence,
        "orphan_experiments": len(orphan_exps),
        "orphan_evidence": len(orphan_evis),
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-merge",
        action="store_true",
        help="Opt in to destructive merge consolidation when two hypotheses "
             "share a canonical hash. Without this flag the script refuses "
             "to run if any merge groups are detected.",
    )
    args = parser.parse_args()

    counts = run_migration(
        hyp_dir=Path(".atlas/hypotheses"),
        exp_dir=Path(".atlas/experiments"),
        evi_dir=Path(".atlas/evidence"),
        meta_path=Path(".atlas/schema_version.json"),
        allow_merge=args.allow_merge,
    )
    if counts.get("orphan_experiments") or counts.get("orphan_evidence"):
        return 1
    print("Integrity check passed: zero orphan references.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
