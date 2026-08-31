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
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
