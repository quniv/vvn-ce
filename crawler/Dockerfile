FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency installation
RUN pip install --no-cache-dir uv

# Install dependencies first (layer-cached until pyproject.toml changes)
COPY pyproject.toml .
RUN uv pip install --system \
    "httpx>=0.28.1" \
    "selectolax>=0.4.9" \
    "sqlalchemy[asyncio]>=2.0.49" \
    "asyncpg>=0.31.0" \
    "pydantic-settings>=2.14.1"

COPY app/ ./app/

CMD ["python", "-m", "app.main"]
