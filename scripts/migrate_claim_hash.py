"""Migrate hypothesis IDs to canonical claim hashing.

Previous: sha256(claim.strip())[:16]
New:      sha256(claim_canonical(claim))[:16]

claim_canonical applies: lower, whitespace-collapse, strip trailing punctuation.
This re-keys all hypothesis files and re-links experiments and evidence.

Safe to run multiple times — skips hypotheses whose ID already matches canonical form.
"""
import json
import os
import sys
from pathlib import Path

# Add src to path so we can import atlas.utils
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from atlas.utils import claim_hash  # noqa: E402

HYP_DIR = Path(".atlas/hypotheses")
EVI_DIR = Path(".atlas/evidence")
EXP_DIR = Path(".atlas/experiments")

if not HYP_DIR.exists():
    print("No .atlas/hypotheses/ directory found. Nothing to migrate.")
    sys.exit(0)

# Phase 1: Build old_id → new_id mapping
mapping: dict[str, str] = {}
merges: dict[str, list[dict]] = {}  # new_id → list of old records that map to it

for f in sorted(HYP_DIR.glob("*.json")):
    data = json.loads(f.read_text())
    old_id = data["id"]
    new_id = claim_hash(data["claim"])
    if old_id == new_id:
        continue  # already canonical
    mapping[old_id] = new_id
    merges.setdefault(new_id, []).append({"old_id": old_id, "claim": data["claim"], "file": f})

print(f"Hypotheses to migrate: {len(mapping)}")

# Phase 2: Detect merges (multiple old IDs → same new ID)
merge_groups = {k: v for k, v in merges.items() if len(v) > 1}
if merge_groups:
    print(f"\n{len(merge_groups)} merge group(s) detected:")
    for new_id, entries in merge_groups.items():
        print(f"  → {new_id}:")
        for e in entries:
            print(f"    {e['old_id']} | {e['claim'][:80]}")
    # For merges: keep first, add claim_variants from others
    for new_id, entries in merge_groups.items():
        primary = entries[0]
        primary_data = json.loads(primary["file"].read_text())
        variants = primary_data.get("claim_variants", [])
        for other in entries[1:]:
            other_data = json.loads(other["file"].read_text())
            variants.append(other_data["claim"])
            other["file"].unlink()
            print(f"  Merged {other['old_id']} into {primary['old_id']} → {new_id}")
        if variants:
            primary_data["claim_variants"] = variants
        primary_data["id"] = new_id
        new_path = HYP_DIR / f"{new_id}.json"
        new_path.write_text(json.dumps(primary_data, indent=2, default=str))
        if primary["file"].name != f"{new_id}.json":
            primary["file"].unlink()
else:
    print("No merges needed — all canonical hashes are unique.")

# Phase 3: Rename non-merge hypotheses
for old_id, new_id in mapping.items():
    if new_id in merge_groups:
        continue  # already handled
    old_path = HYP_DIR / f"{old_id}.json"
    new_path = HYP_DIR / f"{new_id}.json"
    if not old_path.exists():
        continue
    data = json.loads(old_path.read_text())
    data["id"] = new_id
    new_path.write_text(json.dumps(data, indent=2, default=str))
    old_path.unlink()
    print(f"  Migrated: {old_id} → {new_id}")

# Phase 4: Re-link experiments
updated_experiments = 0
for f in sorted(EXP_DIR.glob("*.json")):
    data = json.loads(f.read_text())
    changed = False
    for field in ("hypothesis_id", "hyp_id"):
        if data.get(field) in mapping:
            data[field] = mapping[data[field]]
            changed = True
    if changed:
        f.write_text(json.dumps(data, indent=2, default=str))
        updated_experiments += 1
print(f"Experiment records updated: {updated_experiments}")

# Phase 5: Re-link evidence
updated_evidence = 0
for f in sorted(EVI_DIR.glob("*.json")):
    data = json.loads(f.read_text())
    if data.get("hypothesis_id") in mapping:
        data["hypothesis_id"] = mapping[data["hypothesis_id"]]
        f.write_text(json.dumps(data, indent=2, default=str))
        updated_evidence += 1
print(f"Evidence records updated: {updated_evidence}")

# Phase 6: Write schema version marker
meta_path = Path(".atlas/schema_version.json")
version_data = {"schema_version": 2, "note": "v2: canonical claim hashing (lower+ws-collapse+strip-punct)"}
meta_path.write_text(json.dumps(version_data, indent=2))
print(f"Schema version written: {meta_path}")

# Verification
final_hyps = list(HYP_DIR.glob("*.json"))
final_exps = list(EXP_DIR.glob("*.json"))
final_evis = list(EVI_DIR.glob("*.json"))
print(f"\nFinal counts: {len(final_hyps)} hypotheses, {len(final_exps)} experiments, {len(final_evis)} evidence")

# Verify all experiment/evidence hypothesis_id refs point to existing hypotheses
hyp_ids = {json.loads(f.read_text())["id"] for f in final_hyps}
orphan_exps = []
for f in sorted(EXP_DIR.glob("*.json")):
    d = json.loads(f.read_text())
    ref = d.get("hypothesis_id") or d.get("hyp_id")
    if ref and ref not in hyp_ids:
        orphan_exps.append((f.stem, ref))

orphan_evis = []
for f in sorted(EVI_DIR.glob("*.json")):
    d = json.loads(f.read_text())
    ref = d.get("hypothesis_id")
    if ref and ref not in hyp_ids:
        orphan_evis.append((f.stem, ref))

if orphan_exps:
    print(f"\nWARNING: {len(orphan_exps)} orphan experiment(s): {orphan_exps}")
if orphan_evis:
    print(f"\nWARNING: {len(orphan_evis)} orphan evidence record(s): {orphan_evis}")

if not orphan_exps and not orphan_evis:
    print("Integrity check passed: zero orphan references.")
else:
    sys.exit(1)
