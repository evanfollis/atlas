"""Migrate hypothesis IDs from [:12] to [:16] SHA-256 truncation.

Unifies the state store after the claim_hash() consolidation in utils.py.
Safe to run multiple times — skips already-migrated hypotheses (len==16).
"""
import hashlib
import json
from pathlib import Path

HYP_DIR = Path(".atlas/hypotheses")
EVI_DIR = Path(".atlas/evidence")
EXP_DIR = Path(".atlas/experiments")


def claim_hash_16(claim: str) -> str:
    return hashlib.sha256(claim.strip().encode()).hexdigest()[:16]


# Build old→new mapping for 12-char hypothesis IDs
mapping: dict[str, str] = {}
for f in HYP_DIR.glob("*.json"):
    if len(f.stem) != 12:
        continue  # already [:16], skip
    data = json.loads(f.read_text())
    old_id = data["id"]
    new_id = claim_hash_16(data["claim"])
    mapping[old_id] = new_id

print(f"Hypotheses to migrate: {len(mapping)}")
collisions = []
for old_id, new_id in mapping.items():
    new_path = HYP_DIR / f"{new_id}.json"
    old_path = HYP_DIR / f"{old_id}.json"
    data = json.loads(old_path.read_text())
    if new_path.exists():
        # If existing [:16] file has identical claim, we can just delete the [:12] dupe
        existing = json.loads(new_path.read_text())
        if existing["claim"].strip() == data["claim"].strip():
            old_path.unlink()
            print(f"  Deduplicated (identical claim): {old_id} → {new_id}")
        else:
            collisions.append((old_id, new_id))
            print(f"  COLLISION (different claims): {old_id} → {new_id} — MANUAL REVIEW NEEDED")
        continue
    data["id"] = new_id
    new_path.write_text(json.dumps(data, indent=2, default=str))
    old_path.unlink()
    print(f"  Migrated: {old_id} → {new_id}")

# Update evidence references
updated_evidence = 0
for f in EVI_DIR.glob("*.json"):
    data = json.loads(f.read_text())
    if data.get("hypothesis_id") in mapping:
        data["hypothesis_id"] = mapping[data["hypothesis_id"]]
        f.write_text(json.dumps(data, indent=2, default=str))
        updated_evidence += 1
print(f"Evidence records updated: {updated_evidence}")

# Update experiment references
updated_experiments = 0
for f in EXP_DIR.glob("*.json"):
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

if collisions:
    print(f"\nWARNING: {len(collisions)} collision(s) need manual review: {collisions}")
else:
    print("\nMigration complete — no collisions.")

# Verify
remaining_12 = sum(1 for f in HYP_DIR.glob("*.json") if len(f.stem) == 12)
remaining_16 = sum(1 for f in HYP_DIR.glob("*.json") if len(f.stem) == 16)
print(f"Final: {remaining_16} hypotheses at [:16], {remaining_12} remaining at [:12]")
