from datetime import datetime, date
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, model_validator

OpportunityType = Literal["job", "client", "project", "business", "github"]
OpportunityStatus = Literal["new", "pending_verification", "verified", "ready_to_contact", "contacted", "replied", "quoted", "negotiating", "won", "lost", "saved", "ignored"]
RadarStatus = Literal["active", "paused", "running", "error"]
SourceSlug = Literal["mock", "public_web", "github", "hackernews", "rss", "web_search", "tikhub", "xiaohongshu", "weibo", "zhihu", "douyin", "reddit", "bilibili", "kuaishou", "lemon8", "pipixia", "threads", "twitter", "youtube", "wechat_search", "telegram", "linkedin", "toutiao"]


class SkillInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    level: Literal["beginner", "intermediate", "strong", "expert"] = "intermediate"


class ProfileUpsert(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    identity: str = ""
    location: str = ""
    monthly_income_goal: int = Field(default=0, ge=0)
    minimum_project_budget: int = Field(default=0, ge=0)
    available_hours_per_day: float = Field(default=0, ge=0, le=24)
    skills: list[SkillInput] = []
    goals: list[Literal["job", "client", "project", "business"]] = []


class ProfileRead(ProfileUpsert):
    id: str
    user_id: str


class ProfileAnalyzeRequest(BaseModel):
    text: str = Field(min_length=10, max_length=5000)


class ProfileAnalysis(BaseModel):
    identity: list[str]
    skills: list[SkillInput]
    goals: list[Literal["job", "client", "project", "business"]]
    recommended_directions: list[str]


class QueryPlanItem(BaseModel):
    query: str
    source: SourceSlug = "hackernews"
    priority: int = Field(ge=0, le=100)


from .collection import CollectionPolicy


class RadarCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    goal: str = Field(min_length=1, max_length=2000)
    mode: Literal["general", "acquisition"] = "acquisition"
    minimum_budget: int = Field(default=0, ge=0)
    frequency: str = "daily"
    freshness_hours: int = Field(default=72, ge=1, le=720)
    collection_policy: CollectionPolicy = Field(default_factory=CollectionPolicy)
    keywords: list[str] = []
    locations: list[str] = []
    sources: list[SourceSlug] = ["hackernews"]
    source_config: dict[str, str] = Field(default_factory=dict)
    # Natural-language listener: e.g. "寻找正在抱怨短视频制作太慢、希望批量生产视频的商家"
    listener_description: str = Field(default="", max_length=2000)
    local_schedule_enabled: bool = False

    @model_validator(mode="after")
    def acquisition_goal_is_descriptive(self):
        if self.mode == "acquisition" and len(self.goal.strip()) < 10:
            raise ValueError("Acquisition Radar goal must contain at least 10 characters")
        if self.mode == "general" and self.minimum_budget != 0:
            raise ValueError("General monitoring does not use a minimum budget")
        if any(len(key) > 80 or len(value) > 2048 for key, value in self.source_config.items()):
            raise ValueError("Source configuration is too large")
        if self.source_config.get("lead_hunt") == "true":
            if self.keywords and (len(self.keywords)>3 or len(self.keywords)*len(self.sources)>6 or any(not k.strip() or len(k)>100 for k in self.keywords)):
                raise ValueError("抓单最多3关键词、6次首屏请求，每词1–100字")
            if "hunt_conditions" in self.source_config:
                from .hunt import HuntConditions
                HuntConditions.model_validate_json(self.source_config["hunt_conditions"])
                if self.mode != "general" or not self.keywords or not self.sources or len(set(self.sources)) != len(self.sources):
                    raise ValueError("条件抓单须为通用模式，至少1个平台和关键词，平台不可重复")
                if self.collection_policy.time_basis != "published" or self.collection_policy.include_unknown_dates:
                    raise ValueError("条件抓单必须按原帖发布时间过滤，未知时间不得当新需求")
        return self


class RadarRunStats(BaseModel):
    queries: int = 0
    items_found: int = 0
    duplicates_removed: int = 0
    analyzed: int = 0
    opportunities_found: int = 0
    matched: int = 0
    recommended: int = 0


class RadarRead(RadarCreate):
    id: str
    user_id: str
    status: RadarStatus
    queries: list[QueryPlanItem] = []
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    stats: RadarRunStats = Field(default_factory=RadarRunStats)
    listener_config: dict | None = None


class RadarRunRead(BaseModel):
    id: str
    radar_id: str
    status: Literal["queued", "running", "completed", "partial", "failed"]
    stats: RadarRunStats
    error_message: str | None = None
    error_code: str | None = None
    collector_errors: list[dict] = Field(default_factory=list)
    stage_stats: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RawItem(BaseModel):
    external_id: str
    title: str
    content: str
    url: str
    author: str | None = None
    source: str
    published_at: datetime | None = None
    metadata: dict = {}
    # Money Intelligence extensions: platform-side last activity time (e.g. GitHub
    # pushed_at). Freshness filtering uses max(published_at, updated_at_source).
    updated_at_source: datetime | None = None
    platform: str | None = None
    language: str | None = None
    engagement: dict = {}


class OpportunityAnalysis(BaseModel):
    is_opportunity: bool
    type: OpportunityType
    title: str
    summary: str
    location: str = "线上"
    work_mode: Literal["online", "offline", "hybrid"] = "online"
    skills: list[str] = []
    budget_min: int = Field(ge=0)
    budget_max: int = Field(ge=0)
    estimated_hours: float = Field(gt=0)
    commercial_intent: int = Field(ge=0, le=100)
    skill_match: int = Field(ge=0, le=100)
    conversion_probability: int = Field(ge=0, le=100)
    urgency: int = Field(ge=0, le=100)
    competition: int = Field(ge=0, le=100)
    risk: int = Field(ge=0, le=100)
    reasons: list[str] = []
    warnings: list[str] = []


class OpportunityRead(BaseModel):
    id: str
    radar_id: str
    type: OpportunityType
    title: str
    summary: str
    source: str
    source_url: str
    published_at: datetime | None = None
    location: str
    work_mode: str
    budget_min: int
    budget_max: int
    currency: str = "CNY"
    estimated_hours: float
    estimated_hourly_rate: tuple[int, int]
    match_score: int
    opportunity_score: int
    conversion_probability: int
    risk_score: int
    recommendation: str
    status: OpportunityStatus
    skills: list[str] = []
    reasons: list[str] = []
    warnings: list[str] = []
    # Money Intelligence extensions (all optional so legacy payloads validate)
    pipeline: dict = Field(default_factory=dict)
    actual_revenue: int | None = None
    actual_hours: float | None = None
    closed_at: datetime | None = None
    money_score: int | None = None
    money_breakdown: dict | None = None
    information_edge: int | None = None
    information_edge_breakdown: dict | None = None
    verification_status: str = "unverified"
    evidence_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class OpportunityAction(BaseModel):
    actual_revenue: int | None = Field(default=None, ge=0)
    actual_hours: float | None = Field(default=None, ge=0)
    closed_at: datetime | None = None


class DailyBriefRead(BaseModel):
    date: date
    scanned_count: int
    opportunities_count: int
    recommended_count: int
    potential_income_min: int
    potential_income_max: int
    summary: str
    signals: list[str]
    avoid: list[str]
    actions: list[str]
    # Money Intelligence V2 (additive; legacy fields keep the old contract)
    top_opportunities: list[dict] = []
    rising_trends: list[dict] = []
    pain_points: list[dict] = []
    payment_signals: list[dict] = []
    job_market_signals: list[dict] = []
    tender_signals: list[dict] = []
    content_opportunities: list[dict] = []
    today_actions: list[dict] = []
    brief_version: str = "v2"


class PreferenceState(BaseModel):
    skill_weights: dict[str, float] = Field(default_factory=dict)
    type_weights: dict[str, float] = Field(default_factory=dict)
    source_weights: dict[str, float] = Field(default_factory=dict)
    location_weights: dict[str, float] = Field(default_factory=dict)
    keyword_weights: dict[str, float] = Field(default_factory=dict)
    min_budget_hint: int | None = None
    recommendation_threshold: int | None = None
