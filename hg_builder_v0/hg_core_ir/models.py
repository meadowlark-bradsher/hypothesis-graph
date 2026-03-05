from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Polarity(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class FactStatus(str, Enum):
    ASSERTED = "asserted"
    RETRACTED = "retracted"


class SourceType(str, Enum):
    AUTOMATION = "automation"
    HUMAN = "human"
    DOCUMENT = "document"
    OBSERVATION = "observation"
    MIGRATION = "migration"
    OTHER = "other"


class ConstraintKind(str, Enum):
    IMPLIES = "implies"
    CONFLICTS_WITH = "conflicts_with"


class ValidityV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_version_min: int | None = None
    graph_version_max: int | None = None
    time_start: datetime | None = None
    time_end: datetime | None = None
    environment: str | List[str] | None = None

    @model_validator(mode="after")
    def _validate_bounds(self) -> "ValidityV1":
        if self.graph_version_min is not None and self.graph_version_max is not None:
            if self.graph_version_min > self.graph_version_max:
                raise ValueError("validity.graph_version_min must be <= validity.graph_version_max")
        if self.time_start is not None and self.time_end is not None:
            if self.time_start > self.time_end:
                raise ValueError("validity.time_start must be <= validity.time_end")
        if isinstance(self.environment, list) and not self.environment:
            raise ValueError("validity.environment list cannot be empty")
        return self


class ProvenanceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    source_id: str = Field(min_length=1)
    artifact_ref: str | None = None
    hash: str | None = None
    run_id: str | None = None
    replicate_id: str | None = None


class FactV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="fact_v1")
    fact_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    object_id: str = Field(min_length=1)
    attribute_id: str = Field(min_length=1)
    polarity: Polarity
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    validity: ValidityV1 | None = None
    provenance: ProvenanceV1
    status: FactStatus = FactStatus.ASSERTED
    retracts_fact_id: str | None = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_retraction(self) -> "FactV1":
        if self.status == FactStatus.RETRACTED and not self.retracts_fact_id:
            raise ValueError("retracted facts must set retracts_fact_id")
        if self.status == FactStatus.ASSERTED and self.retracts_fact_id is not None:
            raise ValueError("asserted facts must not set retracts_fact_id")
        return self


class ConstraintV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="constraint_v1")
    constraint_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    kind: ConstraintKind
    lhs_attribute_ids: List[str] = Field(min_length=1)
    rhs_attribute_ids: List[str] = Field(min_length=1)
    validity: ValidityV1 | None = None
    provenance: ProvenanceV1
    meta: Dict[str, Any] = Field(default_factory=dict)


class ManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="manifest_v1")
    run_id: str = Field(min_length=1)
    created_at: datetime
    fact_logs: List[str] = Field(min_length=1)
    constraint_logs: List[str] = Field(default_factory=list)
    overlays: List[str] = Field(default_factory=list)
    description: str | None = None
    meta: Dict[str, Any] = Field(default_factory=dict)
