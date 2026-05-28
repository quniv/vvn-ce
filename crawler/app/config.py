from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CRAWLER_", env_file=".env", extra="ignore")

    db_url: str = "postgresql+asyncpg://vocab:vocab@localhost:5432/vocab"
    concurrency: int = 8
    delay_ms: int = 100
    batch_size: int = 50
    no_raw_html: bool = True
    force: bool = False
    limit: int | None = None
    log_file: str | None = None


settings = Settings()
