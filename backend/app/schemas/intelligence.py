from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

SignalType = Literal[
    "pain_point", "purchase_intent", "hiring", "outsourcing", "product_request",
    "feature_request", "complaint", "price_change", "funding", "policy", "tender",
    "technology_growth", "creator_trend", "consumer_trend", "supply_shortage",
]


class SignalRead(BaseModel):
    id: str = ""
    raw_item_id: str | None = None
    radar_id: str | None = None
    cluster_id: str | None = None
    signal_type: SignalType
    title: str = ""
    entities: list[str] = []
    keywords: list[str] = []
    intent: str | None = None
    sentiment: str | None = None
    commercial_intent: int = Field(default=0, ge=0, le=100)
    payment_evidence: bool = False
    urgency: int = Field(default=0, ge=0, le=100)
    confidence: int = Field(default=0, ge=0, le=100)
    extraction_method: Literal["rule", "llm", "hybrid"] = "rule"
    occurred_at: datetime | None = None
    created_at: datetime | None = None


class EventClusterRead(BaseModel):
    id: str
    radar_id: str | None = None
    title: str = ""
    summary: str = ""
    keyphrases: list[str] = []
    centroid: list[float] | None = None
    source_count: int = 0
    document_count: int = 0
    unique_authors: int = 0
    unique_platforms: int = 0
    velocity_1h: float = 0
    velocity_24h: float = 0
    velocity_7d: float = 0
    velocity_30d: float = 0
    engagement_growth: float = 0
    breakout_score: int = Field(default=0, ge=0, le=100)
    representative_item_ids: list[str] = []
    merged_into: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class TrendTopicRead(BaseModel):
    id: str
    radar_id: str | None = None
    topic: str
    mention_count: int = 0
    engagement: int = 0
    metrics: dict = {}
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class TrendSnapshotRead(BaseModel):
    id: str
    topic_id: str
    captured_at: datetime | None = None
    mention_count: int = 0
    engagement: int = 0
    metrics: dict = {}


class ChangeEventRead(BaseModel):
    id: str
    radar_id: str | None = None
    subject_kind: Literal["topic", "cluster", "source", "keyword"] = "topic"
    subject_key: str
    metric_key: str
    baseline_value: float = 0
    current_value: float = 0
    change_rate: float = 0
    z_score: float = 0
    velocity: float = 0
    acceleration: float = 0
    momentum: float = 0
    breakout_score: int = Field(default=0, ge=0, le=100)
    is_breakout: bool = False
    window_start: datetime | None = None
    window_end: datetime | None = None
    detected_at: datetime | None = None
    dedup_key: str = ""


class SourceHealthRead(BaseModel):
    slug: str
    status: Literal["healthy", "degraded", "unhealthy", "unknown"] = "unknown"
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    runs_total: int = 0
    runs_ok: int = 0
    items_fetched: int = 0
    success_rate: float = 0
    avg_latency_ms: int = 0
    rate_limited_count: int = 0
    error_count: int = 0
    health_score: int = Field(default=100, ge=0, le=100)


class StageStats(BaseModel):
    """Per-run LLM funnel: how many items entered / left each stage."""

    collected: int = 0
    after_dedup: int = 0
    after_freshness: int = 0
    after_known: int = 0
    analyzed: int = 0
    gated_off_topic: int = 0
    gated_low_relevance: int = 0
    gated_by_listener: int = 0
    llm_budget_skipped: int = 0
    semantic_removed: int = 0
    signals_extracted: int = 0
    llm_signals_extracted: int = 0
    clusters_touched: int = 0
    opportunities_found: int = 0
    embedding_ms: int = 0
    embedding_calls: int = 0


class MoneyScoreBreakdown(BaseModel):
    demand_velocity: int = Field(default=0, ge=0, le=100)
    payment_evidence: int = Field(default=0, ge=0, le=100)
    supply_gap: int = Field(default=0, ge=0, le=100)
    profit_margin: int = Field(default=0, ge=0, le=100)
    repeatability: int = Field(default=0, ge=0, le=100)
    competition: int = Field(default=0, ge=0, le=100)
    freshness: int = Field(default=0, ge=0, le=100)
    information_edge: int = Field(default=0, ge=0, le=100)
    execution_difficulty: int = Field(default=0, ge=0, le=100)
    personal_fit: int = Field(default=0, ge=0, le=100)
    confidence: int = Field(default=0, ge=0, le=100)
    weights: dict[str, float] = {}
    total: int = Field(default=0, ge=0, le=100)


class InformationEdgeBreakdown(BaseModel):
    novelty: int = Field(default=0, ge=0, le=100)
    freshness: int = Field(default=0, ge=0, le=100)
    source_rarity: int = Field(default=0, ge=0, le=100)
    cross_source_confirmation: int = Field(default=0, ge=0, le=100)
    demand_growth: int = Field(default=0, ge=0, le=100)
    supply_gap: int = Field(default=0, ge=0, le=100)
    competition_awareness: int = Field(default=0, ge=0, le=100)
    actionability: int = Field(default=0, ge=0, le=100)
    information_half_life_hours: float = 0
    total: int = Field(default=0, ge=0, le=100)


class DailyBriefV2(BaseModel):
    """Additive V2 sections; the legacy DailyBriefRead fields stay untouched."""

    top_opportunities: list[dict] = []
    rising_trends: list[dict] = []
    pain_points: list[dict] = []
    payment_signals: list[dict] = []
    job_market_signals: list[dict] = []
    tender_signals: list[dict] = []
    content_opportunities: list[dict] = []
    today_actions: list[dict] = []
    brief_version: str = "v2"


class RadarListenerConfig(BaseModel):
    """Compiled from a natural-language listener description (openmagpie-style watch)."""

    positive_signals: list[str] = []
    negative_signals: list[str] = []
    search_queries: list[str] = []
    exclusion_rules: list[str] = []


class SignalExtractionPayload(BaseModel):
    """LLM multi-signal extraction output (fast model, cluster level)."""

    signals: list[SignalRead] = []


class PainPointRead(BaseModel):
    id: str
    radar_id: str | None = None
    theme: str
    title: str = ""
    summary: str = ""
    mention_count: int = 0
    growth_rate: float = 0
    platform_count: int = 0
    unique_user_count: int = 0
    severity: int = Field(default=0, ge=0, le=100)
    payment_intent: int = Field(default=0, ge=0, le=100)
    current_solutions: str = ""
    solution_satisfaction: int | None = None
    cluster_id: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
