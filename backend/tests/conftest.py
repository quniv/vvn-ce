import os

# Must be set before any app module is imported — pydantic-settings reads them at Settings() init time.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://vocab:vocab@localhost:5432/vocab_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
