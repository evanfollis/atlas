"""ReasoningPrimitive — validated atomic claim promoted from evidence."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class ReasoningPrimitive(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    claim: str  # The validated statement
    hypothesis_id: str  # Origin hypothesis
    evidence_ids: list[str]  # Supporting evidence
    confidence: float  # 0-1, derived from evidence quality
    domain: str = "crypto"
    tags: list[str] = Field(default_factory=list)
    causal_parents: list[str] = Field(default_factory=list)  # Primitive IDs this depends on
    causal_children: list[str] = Field(default_factory=list)  # Primitives that depend on this
