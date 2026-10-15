"""Post-fetch gates shared by manual collection and saved Radars."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class CollectionPolicy(BaseModel):
    model_config = {"extra": "forbid"}
    required_terms: list[str] = Field(default_factory=list, max_length=20)
    excluded_terms: list[str] = Field(default_factory=list, max_length=20)
    match_mode: Literal["any", "all"] = "any"
    time_basis: Literal["published", "activity"] = "activity"
    include_unknown_dates: bool = True
    sort: Literal["latest", "hot"] = "latest"
    activity_filter: Literal["any", "author", "discussion"] = "any"
    min_interactions: int = Field(default=0, ge=0, le=10_000_000)

    @field_validator("required_terms", "excluded_terms")
    @classmethod
    def valid_terms(cls, terms):
        if any(not term.strip() or len(term) > 100 for term in terms):
            raise ValueError("Terms must contain 1 to 100 characters")
        return list(dict.fromkeys(term.strip() for term in terms))
