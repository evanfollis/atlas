"""ResearchCycle — durable session unit for hypothesis investigation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class CycleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class CycleOutcome(str, Enum):
    PROMOTED = "promoted"
    KILLED = "killed"
    PIVOTED = "pivoted"


class ResearchCycle(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    hypothesis_id: str
    status: CycleStatus = CycleStatus.ACTIVE
    outcome: Optional[CycleOutcome] = None
    experiment_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    decision_rationale: str = ""


class ReentrySnapshot(BaseModel):
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_hypothesis: str
    active_experiments: list[str]
    evidence_collected: int
    graph_node_count: int = 0
    next_action: str = ""
