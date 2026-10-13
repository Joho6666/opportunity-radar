from datetime import datetime
from typing import Literal
import json
from pydantic import BaseModel, Field, field_validator
from .domain import OpportunityStatus


class PipelinePatch(BaseModel):
    model_config = {"extra": "forbid"}
    status: OpportunityStatus | None = None
    service_type: str | None = Field(default=None,max_length=100)
    next_follow_up_at: datetime | None = None
    clear_follow_up: bool = False
    notes: str | None = Field(default=None,max_length=3000)
    actual_revenue: int | None = Field(default=None,ge=0)
    actual_cost: float | None = Field(default=None,ge=0,le=1_000_000_000,allow_inf_nan=False)
    actual_hours: float | None = Field(default=None,ge=0,le=100000,allow_inf_nan=False)
    loss_reason: str | None = Field(default=None,max_length=2000)
    verification_status: Literal["unverified","verified","invalidated","disputed"] | None = None
    public_contact_channel: str | None = Field(default=None,max_length=300)
    quote_draft: dict | None = None
    communication_draft: str | None = Field(default=None,max_length=3000)

    @field_validator("quote_draft")
    @classmethod
    def bounded_quote(cls, value):
        if value is not None and len(json.dumps(value,allow_nan=False).encode()) > 32768:
            raise ValueError("Quote draft exceeds 32 KiB")
        return value


class QuoteRequest(BaseModel):
    model_config = {"extra": "forbid"}
    hourly_rate: float = Field(gt=0,le=100000,allow_inf_nan=False)
    estimated_hours: float = Field(gt=0,le=10000,allow_inf_nan=False)
    direct_cost: float = Field(default=0,ge=0,le=1000000,allow_inf_nan=False)
    service_type: str = Field(min_length=1,max_length=100)
    scope: str = Field(min_length=10,max_length=2000)
    delivery_days: int = Field(default=7,ge=1,le=365)
