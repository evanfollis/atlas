"""Evidence — typed observation from experiments."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EvidenceClass(str, Enum):
    BACKTEST_RESULT = "backtest_result"
    OUT_OF_SAMPLE_TEST = "out_of_sample_test"
    STATISTICAL_TEST = "statistical_test"
    LIVE_OBSERVATION = "live_observation"
    EXTERNAL_PUBLICATION = "external_publication"


class EvidenceQuality(str, Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class EvidenceDirection(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    INCONCLUSIVE = "inconclusive"


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    experiment_id: str
    hypothesis_id: str
    evidence_class: EvidenceClass
    quality: EvidenceQuality
    direction: EvidenceDirection
    summary: str  # Human-readable description of finding
    statistics: dict[str, Any] = Field(default_factory=dict)  # p-value, sharpe, CI, etc.
    data_range: str = ""  # e.g. "2023-01-01 to 2024-06-30"
