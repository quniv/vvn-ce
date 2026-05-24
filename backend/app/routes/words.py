from datetime import datetime, time, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.word import Word
from app.schemas.word import (
    ExplainRequest,
    ExplainResponse,
    KeywordItem,
    SaveKeywordsRequest,
    VoteRequest,
    WordRead,
)
from app.services.cache import cache_get, cache_key, cache_set
from app.services.openrouter import (
    OpenRouterError,
    SentenceResponse,
    WordResponse,
    explain as call_openrouter,
)

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _today_range() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
    return start, end


def _is_wordish(text: str) -> bool:
    """A 'wordish' input is short enough that DB dedupe by exact text makes sense."""
    return len(text.strip().split()) <= 2


async def _find_word_in_db(db: AsyncSession, text: str) -> Word | None:
    """Case-insensitive lookup by text."""
    result = await db.execute(
        select(Word).where(func.lower(Word.text) == text.strip().lower()).limit(1)
    )
    return result.scalar_one_or_none()


async def _bump_query_count(db: AsyncSession, word_id: UUID) -> Word | None:
    """Increment query_count and update last_queried_at; returns the updated row."""
    result = await db.execute(
        update(Word)
        .where(Word.id == word_id)
        .values(query_count=Word.query_count + 1, last_queried_at=func.now())
        .returning(Word)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await db.commit()
    return row


async def _upsert_word(
    db: AsyncSession,
    response: WordResponse,
    *,
    source_url: str | None,
    source_sentence: str | None,
    model: str,
) -> Word:
    """INSERT or UPDATE based on case-insensitive text. Returns the row."""
    insert_stmt = pg_insert(Word).values(
        text=response.text,
        word_type=response.word_type,
        pronunciation=response.pronunciation,
        explanation=response.explanation,
        example=response.example,
        synonyms=response.synonyms,
        collocations=response.collocations,
        difficulty=response.difficulty,
        source_url=source_url,
        source_sentence=source_sentence,
        model_source=model,
    )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=[func.lower(Word.text)],
        set_={
            "query_count": Word.query_count + 1,
            "last_queried_at": func.now(),
            # Refresh the LLM-derived content too — the new call presumably
            # produced equivalent (or better) data.
            "explanation": insert_stmt.excluded.explanation,
            "synonyms": insert_stmt.excluded.synonyms,
            "collocations": insert_stmt.excluded.collocations,
            "difficulty": insert_stmt.excluded.difficulty,
            "example": insert_stmt.excluded.example,
            "pronunciation": insert_stmt.excluded.pronunciation,
            "word_type": insert_stmt.excluded.word_type,
            "model_source": insert_stmt.excluded.model_source,
        },
    ).returning(Word)

    result = await db.execute(upsert_stmt)
    row = result.scalar_one()
    await db.commit()
    return row


def _explain_response_from_row(
    row: Word, *, cached: bool, db_hit: bool, model: str
) -> ExplainResponse:
    return ExplainResponse(
        kind="word",
        text=row.text,
        word_type=row.word_type,
        pronunciation=row.pronunciation,
        explanation=row.explanation,
        example=row.example,
        synonyms=row.synonyms or [],
        collocations=row.collocations or [],
        difficulty=row.difficulty,
        keywords=[],
        saved=True,
        saved_id=row.id,
        model_source=row.model_source or model,
        up_vote=row.up_vote,
        down_vote=row.down_vote,
        query_count=row.query_count,
        cached=cached,
        db_hit=db_hit,
    )


def _cached_blob_to_word_response(blob: dict) -> WordResponse | None:
    if blob.get("kind") != "word":
        return None
    try:
        return WordResponse.model_validate(blob)
    except Exception:
        return None


@router.post("/explain", response_model=ExplainResponse)
async def explain(req: ExplainRequest, db: DbDep) -> ExplainResponse:
    model = settings.openrouter_model
    key = cache_key(model, req.text)

    # 1. Redis cache
    cached_blob = await cache_get(key)
    if cached_blob is not None:
        kind = cached_blob.get("kind")
        if kind == "word":
            word_resp = _cached_blob_to_word_response(cached_blob)
            if word_resp is not None:
                row = await _upsert_word(
                    db, word_resp,
                    source_url=req.source_url, source_sentence=None, model=model,
                )
                return _explain_response_from_row(
                    row, cached=True, db_hit=False, model=model,
                )
        elif kind == "sentence":
            try:
                sentence_resp = SentenceResponse.model_validate(cached_blob)
            except Exception:
                sentence_resp = None
            if sentence_resp is not None:
                return ExplainResponse(
                    kind="sentence",
                    text=sentence_resp.text,
                    explanation=sentence_resp.explanation,
                    keywords=[KeywordItem.model_validate(k.model_dump()) for k in sentence_resp.keywords],
                    saved=False,
                    model_source=model,
                    cached=True,
                )

    # 2. Postgres (only for wordish inputs)
    if _is_wordish(req.text):
        existing = await _find_word_in_db(db, req.text)
        if existing is not None:
            bumped = await _bump_query_count(db, existing.id)
            row = bumped or existing
            # Hydrate Redis so the next call is a Redis hit
            word_resp = WordResponse(
                kind="word",
                text=row.text,
                word_type=row.word_type,
                pronunciation=row.pronunciation,
                explanation=row.explanation,
                example=row.example,
                synonyms=row.synonyms or [],
                collocations=row.collocations or [],
                difficulty=row.difficulty,
            )
            await cache_set(
                key,
                word_resp.model_dump(mode="json"),
                ttl_seconds=settings.cache_ttl_seconds,
            )
            return _explain_response_from_row(
                row, cached=False, db_hit=True, model=model,
            )

    # 3. LLM
    try:
        response = await call_openrouter(req.text)
    except OpenRouterError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    await cache_set(key, response.model_dump(mode="json"), ttl_seconds=settings.cache_ttl_seconds)

    if isinstance(response, WordResponse):
        row = await _upsert_word(
            db, response,
            source_url=req.source_url, source_sentence=None, model=model,
        )
        return _explain_response_from_row(
            row, cached=False, db_hit=False, model=model,
        )

    # Sentence
    assert isinstance(response, SentenceResponse)
    return ExplainResponse(
        kind="sentence",
        text=response.text,
        explanation=response.explanation,
        keywords=[KeywordItem.model_validate(k.model_dump()) for k in response.keywords],
        saved=False,
        model_source=model,
        cached=False,
    )


@router.post("/words/save", response_model=list[WordRead])
async def save_keywords(req: SaveKeywordsRequest, db: DbDep) -> list[Word]:
    """UPSERT each selected keyword, deduping by LOWER(text)."""
    model = settings.openrouter_model
    saved: list[Word] = []
    for k in req.keywords:
        word_resp = WordResponse(
            kind="word",
            text=k.text,
            word_type=k.word_type,
            pronunciation=k.pronunciation,
            explanation=k.explanation,
            example=k.example,
            synonyms=k.synonyms,
            collocations=k.collocations,
            difficulty=k.difficulty,
        )
        row = await _upsert_word(
            db, word_resp,
            source_url=req.source_url,
            source_sentence=req.source_sentence,
            model=model,
        )
        saved.append(row)
    return saved


@router.get("/words/today", response_model=list[WordRead])
async def words_today(db: DbDep) -> list[Word]:
    start, end = _today_range()
    result = await db.execute(
        select(Word)
        .where(Word.last_queried_at >= start)
        .where(Word.last_queried_at <= end)
        .order_by((Word.up_vote - Word.down_vote).desc(), Word.last_queried_at.desc())
    )
    return list(result.scalars().all())


@router.get("/words", response_model=list[WordRead])
async def words_all(db: DbDep, limit: int = 1000) -> list[Word]:
    result = await db.execute(
        select(Word)
        .order_by((Word.up_vote - Word.down_vote).desc(), Word.last_queried_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("/words/{word_id}/vote", response_model=WordRead)
async def vote_word(word_id: UUID, req: VoteRequest, db: DbDep) -> Word:
    column = Word.up_vote if req.direction == "up" else Word.down_vote
    stmt = (
        update(Word)
        .where(Word.id == word_id)
        .values({column: column + 1})
        .returning(Word)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Word not found")
    await db.commit()
    return row
