"""Public evidence ingestion contracts."""

from ..services.evidence_ingest import EvidenceBatch, EvidenceCategory, EvidenceInput, EvidenceRecord, EvidenceUpsertResult
from pydantic import BaseModel, Field
from typing import Literal

class EvidenceReview(BaseModel):
    model_config = {"extra": "forbid"}
    verification_status: Literal["unverified", "verified", "invalidated", "disputed"] | None = None
    category: EvidenceCategory | None = None
    title: str | None = Field(default=None,max_length=200)
    summary: str | None = Field(default=None,max_length=2000)
    budget_min: int | None = Field(default=None,ge=0)
    budget_max: int | None = Field(default=None,ge=0)
    notes: str | None = Field(default=None, max_length=2000)



class EvidenceConversion(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)

__all__ = ["EvidenceBatch", "EvidenceCategory", "EvidenceInput", "EvidenceRecord", "EvidenceUpsertResult", "EvidenceReview", "EvidenceConversion"]
