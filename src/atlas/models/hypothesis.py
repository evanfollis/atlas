"""Hypothesis — specialization of CriticalAssumption for research."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class HypothesisStatus(str, Enum):
    FORMULATED = "formulated"
    TESTING = "testing"
    SUPPORTED = "supported"
    FALSIFIED = "falsified"
    PROMOTED = "promoted"


class Hypothesis(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    claim: str  # The falsifiable statement
    rationale: str  # Why we believe this might be true
    falsification_criteria: str  # What would prove it wrong
    significance_threshold: float = 0.05  # Pre-registered alpha
    domain: str = "crypto"
    tags: list[str] = Field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.FORMULATED
    parent_primitive_id: Optional[str] = None  # If derived from existing knowledge
