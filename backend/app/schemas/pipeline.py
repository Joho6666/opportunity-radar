from datetime import datetime
from typing import Literal
import json
from pydantic import BaseModel, Field, field_validator
from .domain import OpportunityStatus


class FollowUpEvent(BaseModel):
    model_config = {"extra": "forbid"}
    request_id: str = Field(min_length=8,max_length=100)
    kind: Literal["note","contact","reply","quote_sent","payment"] = "note"
    text: str = Field(min_length=1,max_length=3000)
    quote_version: int | None = Field(default=None,ge=0)


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
    quote_request_id: str | None = Field(default=None,min_length=8,max_length=100)
    expected_quote_version: int | None = Field(default=None,ge=0)
    follow_up_event: FollowUpEvent | None = None
    communication_draft: str | None = Field(default=None,max_length=3000)

    @field_validator("quote_draft")
    @classmethod
    def bounded_quote(cls, value):
        if value is not None and len(json.dumps(value,allow_nan=False).encode()) > 32768:
            raise ValueError("Quote draft exceeds 32 KiB")
        return value


class QuotePackage(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1,max_length=40)
    quantity: int = Field(ge=1,le=100000)
    deliverables: list[str] = Field(min_length=1,max_length=20)
    scope: str = Field(min_length=10,max_length=2000)
    exclusions: str = Field(min_length=1,max_length=2000)
    revisions: int = Field(ge=0,le=100)
    estimated_hours: float = Field(gt=0,le=10000,allow_inf_nan=False)
    delivery_days: int = Field(ge=1,le=365)

    @field_validator("deliverables")
    @classmethod
    def bounded_deliverables(cls,value):
        if any(not x.strip() or len(x)>500 for x in value):raise ValueError("Invalid deliverable")
        return value


class PaymentMilestone(BaseModel):
    model_config = {"extra": "forbid"}
    label: str = Field(min_length=1,max_length=100)
    percent: float = Field(gt=0,le=100,allow_inf_nan=False)


class QuoteRequest(BaseModel):
    model_config = {"extra": "forbid"}
    hourly_rate: float = Field(gt=0,le=100000,allow_inf_nan=False)
    estimated_hours: float = Field(gt=0,le=10000,allow_inf_nan=False)
    direct_cost: float = Field(default=0,ge=0,le=1000000,allow_inf_nan=False)
    service_type: str = Field(min_length=1,max_length=100)
    scope: str = Field(min_length=10,max_length=2000)
    delivery_days: int = Field(default=7,ge=1,le=365)
    internal_hourly_cost: float | None = Field(default=None,ge=0,le=100000,allow_inf_nan=False)
    valid_days: int = Field(default=14,ge=1,le=365)
    packages: list[QuotePackage] | None = Field(default=None,min_length=3,max_length=3)
    payment_milestones: list[PaymentMilestone] = Field(default_factory=lambda:[PaymentMilestone(label="确认范围后预付款",percent=50),PaymentMilestone(label="验收交付后尾款",percent=50)],min_length=1,max_length=10)

    @field_validator("payment_milestones")
    @classmethod
    def percent_total(cls,value):
        if abs(sum(x.percent for x in value)-100)>.001:raise ValueError("Payment percentages must total 100")
        return value
