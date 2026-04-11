"""Experiment — specialization of Probe for research."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ExperimentStatus(str, Enum):
    DESIGNED = "designed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Experiment(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    hypothesis_id: str
    description: str  # What we're doing
    method: str  # How (backtest, statistical test, observation)
    parameters: dict[str, Any] = Field(default_factory=dict)  # Exchange, pair, timeframe, etc.
    success_criteria: str  # What constitutes support
    failure_criteria: str  # What constitutes falsification
    status: ExperimentStatus = ExperimentStatus.DESIGNED
    results: Optional[dict[str, Any]] = None  # Populated after execution
