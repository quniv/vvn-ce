from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import engine
from app.routes import game, health, words
from app.services.cache import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await close_redis()
        await engine.dispose()


app = FastAPI(title="Vocab CE Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(words.router, prefix="/api", tags=["words"])
app.include_router(game.router, prefix="/api", tags=["game"])

# Developer-only routes — only mounted when DEBUG=true in .env
if settings.debug:
    from app.routes import dev  # noqa: WPS433 — conditional import is intentional
    app.include_router(dev.router, prefix="/api", tags=["dev"])
