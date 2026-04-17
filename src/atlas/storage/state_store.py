"""Shared state management with pre-registration immutability enforcement.

Both the CLI and AutonomousRunner must use this module to persist domain
objects.  The runner's previous _save_obj bypassed immutability guards —
this module closes that gap.

Atomicity: save() writes to a tmpfile in the same directory then renames
it to the target path.  os.replace() is atomic on Linux (single filesystem),
so readers never observe a partial write.  Two concurrent workers writing the
same object will both succeed; last-write-wins.  For hypotheses and
experiments this is benign (both writers have identical pre-registered
content).  For evidence the deterministic ID in ingest.py makes the
content logically equivalent (modulo created_at).
"""

import json
import os
import tempfile
from pathlib import Path


# Fields that must not change after initial creation (pre-registration integrity)
IMMUTABLE_FIELDS: dict[str, set[str]] = {
    "hypotheses": {"claim", "rationale", "falsification_criteria", "significance_threshold"},
    "experiments": {"hypothesis_id", "description", "method", "success_criteria", "failure_criteria", "parameters"},
}


class StateStore:
    """JSON-per-object storage with immutability guards on pre-registered fields."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, kind: str, obj_id: str, data: dict) -> None:
        d = self.base_dir / kind
        d.mkdir(exist_ok=True)
        path = d / f"{obj_id}.json"

        if path.exists() and kind in IMMUTABLE_FIELDS:
            with open(path) as f:
                existing = json.load(f)
            for field in IMMUTABLE_FIELDS[kind]:
                if field in existing and field not in data:
                    raise ValueError(
                        f"Cannot omit pre-registered field '{field}' on {kind}/{obj_id}"
                    )
                if field in existing and field in data and str(existing[field]) != str(data[field]):
                    raise ValueError(
                        f"Cannot modify pre-registered field '{field}' on {kind}/{obj_id}"
                    )

        # Atomic write: tmpfile in same directory → os.replace (rename).
        # Ensures readers never see a partial write.
        tmp_fd, tmp_name = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def load(self, kind: str, obj_id: str) -> dict | None:
        p = self.base_dir / kind / f"{obj_id}.json"
        if p.exists():
            with open(p) as f:
                return json.load(f)
        return None

    def list_all(self, kind: str) -> list[dict]:
        d = self.base_dir / kind
        if not d.exists():
            return []
        objs = []
        for p in sorted(d.glob("*.json")):
            if p.suffix == ".json":
                with open(p) as f:
                    objs.append(json.load(f))
        return objs
