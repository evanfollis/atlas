"""Append-only ledger for forward predictions.

Mirrors the methodology/revalidation pattern: append-only JSONL, deduplicated
on read by id (last-write-wins), so concurrent or repeated appends are benign
and a resolution simply appends an updated record over the open one. The
single-process production assumption holds; no file locking (consistent with
the rest of atlas storage).
"""

import json
from datetime import datetime
from pathlib import Path

from atlas.models.prediction import Prediction


class PredictionStore:
    def __init__(self, path: Path) -> None:
        self.path = path  # predictions.jsonl

    def append(self, prediction: Prediction) -> None:
        with open(self.path, "a") as f:
            f.write(prediction.model_dump_json() + "\n")

    def all(self) -> list[Prediction]:
        """Latest record per id (last write wins)."""
        if not self.path.exists():
            return []
        latest: dict[str, Prediction] = {}
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                p = Prediction.model_validate_json(line)
                latest[p.id] = p
        return list(latest.values())

    def exists(self, prediction_id: str) -> bool:
        return any(p.id == prediction_id for p in self.all())

    def list_open(self) -> list[Prediction]:
        return [p for p in self.all() if p.status == "open"]

    def count_open(self) -> int:
        return len(self.list_open())

    def list_due(self, now: datetime) -> list[Prediction]:
        """Open predictions whose forward window has closed and can be scored (2b)."""
        return [p for p in self.all() if p.status == "open" and p.resolve_ts <= now]

    def update(self, prediction: Prediction) -> None:
        """Append an updated record; `all()` resolves to it via last-write-wins."""
        self.append(prediction)
