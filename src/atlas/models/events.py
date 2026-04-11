"""Append-only session events for research cycles."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    HYPOTHESIS_FORMULATED = "hypothesis_formulated"
    EXPERIMENT_DESIGNED = "experiment_designed"
    EXPERIMENT_EXECUTED = "experiment_executed"
    EVIDENCE_RECORDED = "evidence_recorded"
    DECISION_MADE = "decision_made"
    PRIMITIVE_PROMOTED = "primitive_promoted"
    GRAPH_UPDATED = "graph_updated"


class SessionEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str
    event_type: EventType
    details: dict[str, Any] = Field(default_factory=dict)
