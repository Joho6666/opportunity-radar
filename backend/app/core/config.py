from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    auth_disabled: bool = False
    local_user_id: str = "00000000-0000-0000-0000-000000000001"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_fast_model: str = ""
    firecrawl_api_key: str = ""
    github_token: str = ""
    tikhub_api_key: str = ""
    # api.tikhub.dev is TikHub's mainland-China endpoint; api.tikhub.io works through a proxy.
    tikhub_base_url: str = "https://api.tikhub.io"
    rss_feeds: str = "https://hnrss.org/newest,https://github.blog/feed/"
    redis_url: str = ""
    # Trust 198.18.0.0/15 DNS answers from a local fake-IP proxy (Clash/Mihomo TUN). Local use only.
    allow_fake_ip_dns: bool = False
    cors_origins: str = "http://127.0.0.1:3001,http://localhost:3000"
    use_in_memory_store: bool = True
    enable_ai_classification: bool = False
    paid_api_enabled: bool = False
    paid_daily_cost_limit: float = Field(default=1.0,gt=0,allow_inf_nan=False)
    paid_daily_request_limit: int = Field(default=20,ge=1,le=100000)
    tikhub_price_per_request: float = 0.0
    firecrawl_price_per_request: float = 0.0
    embedding_price_per_mtok: float = 0.0
    llm_max_output_tokens: int = Field(default=800,ge=1,le=16000)
    allow_retention_delete: bool = False
    # Money Intelligence settings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    simhash_distance_threshold: int = 6
    cluster_similarity_threshold: float = 0.82
    breakout_z_threshold: float = 3.0
    breakout_min_baseline: float = 2.0
    money_score_weights_json: str = ""
    information_edge_weights_json: str = ""
    # P0 cost-funnel gates
    relevance_similarity_threshold: float = 0.30
    enable_relevance_gate: bool = True
    llm_price_input_per_mtok: float = 0.0
    llm_price_output_per_mtok: float = 0.0
    # P1 guardrails
    llm_daily_token_budget: int = 0  # 0 = unlimited
    retention_raw_items_days: int = 90  # 0 = keep forever
    retention_llm_calls_days: int = 30  # 0 = keep forever
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_runtime() -> None:
    """The same production gate applies to API, scheduler and workers."""
    import os
    settings = get_settings()
    if settings.app_env.lower() not in {"prod", "production"}:
        return
    if settings.auth_disabled or settings.use_in_memory_store or not settings.database_url or not settings.supabase_jwt_secret:
        raise RuntimeError("Production requires PostgreSQL and JWT authentication; AUTH_DISABLED is forbidden")
    if os.getenv("INCLUDE_MOCK_COLLECTOR", "false").lower() != "false" or settings.allow_fake_ip_dns:
        raise RuntimeError("Production disallows mock collectors and fake-IP DNS")
