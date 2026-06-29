import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import models  # noqa: F401 — registers all models with Base.metadata
from app.db import Base, get_db
from app.main import app

_TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://vocab:vocab@localhost:5432/vocab_test",
)


@pytest_asyncio.fixture(scope="session")
async def engine():
    e = create_async_engine(_TEST_DB_URL, echo=False)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Functional unique index created by Alembic (not expressible in model metadata)
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_words_lower_text"
                " ON words (LOWER(text))"
            )
        )
    yield e
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await e.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(engine):
    """Delete all rows after every test to give each test a clean slate."""
    yield
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db):
    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
