from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    openrouter_api_key: str = ""
    openrouter_model: str = "z-ai/glm-4.5-air:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    debug: bool = False
    cors_origins: list[str] = ["*"]
    cache_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days
    use_llm_fallback: bool = False  # set USE_LLM_FALLBACK=true in .env to re-enable LLM

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
