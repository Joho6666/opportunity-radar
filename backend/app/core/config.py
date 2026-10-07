from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_fast_model: str = ""
    firecrawl_api_key: str = ""
    github_token: str = ""
    rss_feeds: str = "https://hnrss.org/newest,https://github.blog/feed/"
    redis_url: str = ""
    cors_origins: str = "http://127.0.0.1:3001,http://localhost:3000"
    use_in_memory_store: bool = True
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
