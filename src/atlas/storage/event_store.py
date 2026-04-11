"""Append-only JSONL event store, one file per session."""

import json
from pathlib import Path

from atlas.models.events import SessionEvent


class EventStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        return self.base_dir / f"{session_id}.jsonl"

    def append(self, event: SessionEvent) -> None:
        path = self._session_path(event.session_id)
        with open(path, "a") as f:
            f.write(event.model_dump_json() + "\n")

    def load_session(self, session_id: str) -> list[SessionEvent]:
        path = self._session_path(session_id)
        if not path.exists():
            return []
        events = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(SessionEvent.model_validate_json(line))
        return events

    def list_sessions(self) -> list[str]:
        return [p.stem for p in sorted(self.base_dir.glob("*.jsonl"))]
