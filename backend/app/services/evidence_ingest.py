from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator, computed_field, field_validator

EvidenceCategory = Literal["buyer", "seller", "job", "content", "market"]
EvidenceGrade = Literal["A", "B", "C"]


class EvidenceInput(BaseModel):
    source: str = Field(min_length=1, max_length=80)
    url: HttpUrl
    raw_text: str = Field(min_length=10, max_length=100_000)
    query: str = Field(default="", max_length=500)
    external_id: str | None = Field(default=None, max_length=300)
    published_at: datetime | None = None
    captured_at: datetime | None = None
    category: EvidenceCategory = "market"
    buyer_type: str | None = Field(default=None, max_length=120)
    problem: str | None = Field(default=None, max_length=500)
    payment_signal: str | None = Field(default=None, max_length=500)
    urgency_signal: str | None = Field(default=None, max_length=500)
    metadata: dict[str, str] = Field(default_factory=dict)
    evidence_grade: EvidenceGrade = "C"
    classification_source: str = Field(default="unclassified", max_length=40)
    classification_reason: str = Field(default="", max_length=300)
    classification_confidence: float = Field(default=0.0, ge=0, le=1)
    source_platform: str = Field(default="", max_length=80)
    acquisition_tool: str = Field(default="", max_length=80)

    @field_validator("metadata")
    @classmethod
    def human_fields_are_server_owned(cls,value):
        if {"human_label_digest","human_label_at","qualification_review","label_group"} & value.keys():
            raise ValueError("Human review metadata may only be written through the review endpoint")
        return value


class EvidenceBatch(BaseModel):
    batch_id: str = Field(min_length=1, max_length=120)
    items: list[EvidenceInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def bounded_batch(self):
        if sum(len(item.raw_text) for item in self.items) > 2_000_000:
            raise ValueError("Evidence batch exceeds 2 million characters")
        return self



class EvidenceRecord(BaseModel):
    evidence_id: str
    identity_key: str
    batch_id: str
    source: str
    url: HttpUrl
    raw_text: str
    query: str = ""
    external_id: str | None = None
    published_at: datetime | None = None
    captured_at: datetime
    category: EvidenceCategory = "market"
    buyer_type: str | None = None
    problem: str | None = None
    payment_signal: str | None = None
    urgency_signal: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    evidence_grade: str = "C"
    verification_status: str = "unverified"
    classification_source: str = "unclassified"
    classification_reason: str = ""
    classification_confidence: float = Field(default=0.0, ge=0, le=1)
    source_platform: str = ""
    acquisition_tool: str = ""
    notes: str = ""
    converted_opportunity_id: str | None = None

    @computed_field
    @property
    def assessment(self) -> dict:
        from .demand_qualification import qualification
        return qualification(self.raw_text,self.metadata)


class EvidenceUpsertResult(BaseModel):
    batch_id: str
    inserted: int
    duplicates: int
    records: list[EvidenceRecord]


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "&".join(p for p in parts.query.split("&") if not p.startswith(("utm_", "xsec_", "fbclid=", "gclid="))), ""))


def evidence_identity(item: EvidenceInput) -> str:
    identity = item.external_id if item.external_id else _canonical_url(str(item.url))
    return hashlib.sha256(f"{item.source}|{identity}".encode("utf-8")).hexdigest()


def normalize_evidence(batch: EvidenceBatch, now: datetime | None = None) -> list[EvidenceRecord]:
    """Normalize a batch and remove duplicate evidence without discarding raw text."""
    captured_at = now or datetime.now(timezone.utc)
    result: list[EvidenceRecord] = []
    seen: set[str] = set()
    for item in batch.items:
        identity = evidence_identity(item)
        if identity in seen:
            continue
        seen.add(identity)
        evidence_id = hashlib.sha256(f"{batch.batch_id}|{identity}".encode("utf-8")).hexdigest()[:24]
        payload = item.model_dump()
        # Extract facts from source text even on manual import; supplied metadata
        # cannot turn unknown budgets or deadlines into source-stated facts.
        import json
        from .evidence_facts import facts
        payload["metadata"]={**payload["metadata"],"facts":json.dumps(facts(item.raw_text),ensure_ascii=False)}
        payload["identity_key"] = identity
        payload["batch_id"] = batch.batch_id
        payload["captured_at"] = item.captured_at or captured_at
        result.append(
            EvidenceRecord(
                **payload,
                evidence_id=evidence_id,
            )
        )
    return result
