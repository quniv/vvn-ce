from datetime import datetime, time, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.vote import WordVote
from app.models.word import Word
from app.routes.auth_deps import current_user_email, require_user_email
from app.schemas.word import (
    ExplainRequest,
    ExplainResponse,
    KeywordItem,
    SaveKeywordsRequest,
    VoteRequest,
    WordRead,
)
from app.services.cache import cache_get, cache_key, cache_set
from app.services.google_translate import (
    GoogleTranslateError,
    translate as call_google_translate,
)
from app.services.openrouter import (
    OpenRouterError,
    SentenceResponse,
    WordResponse,
    explain as call_openrouter,
)
from app.services.vdict import (
    fetch_and_parse,
    lookup_in_db as vdict_lookup_in_db,
    upsert_to_db as vdict_upsert_to_db,
    vdict_to_explain_response,
)

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]
EmailOptDep = Annotated[str | None, Depends(current_user_email)]
EmailReqDep = Annotated[str, Depends(require_user_email)]


def _today_range() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
    return start, end


def _is_wordish(text: str) -> bool:
    return len(text.strip().split()) <= 2


# ── Vote aggregation helpers ───────────────────────────────────────

def _vote_aggregates_subquery():
    """Returns a selectable for use as `.add_columns(...)`:
    (up_count_sq, down_count_sq) where each is a correlated scalar subquery
    counting `word_votes.direction = 'up' | 'down'` for the outer Word.id.
    """
    up = (
        select(func.count(WordVote.id))
        .where(and_(WordVote.word_id == Word.id, WordVote.direction == "up"))
        .correlate(Word)
        .scalar_subquery()
    )
    down = (
        select(func.count(WordVote.id))
        .where(and_(WordVote.word_id == Word.id, WordVote.direction == "down"))
        .correlate(Word)
        .scalar_subquery()
    )
    return up, down


def _user_vote_subquery(user_email: str | None):
    """Returns a correlated scalar subquery for the current user's vote,
    or a constant NULL when no user is authenticated."""
    if not user_email:
        # SQL literal NULL cast to text
        from sqlalchemy import literal_column

        return literal_column("CAST(NULL AS TEXT)").label("user_vote")
    return (
        select(WordVote.direction)
        .where(and_(WordVote.word_id == Word.id, WordVote.user_email == user_email))
        .correlate(Word)
        .scalar_subquery()
    )


async def _word_with_aggregates(
    db: AsyncSession, word_id: UUID, user_email: str | None
) -> tuple[Word, int, int, str | None] | None:
    up_sq, down_sq = _vote_aggregates_subquery()
    user_vote_sq = _user_vote_subquery(user_email)
    stmt = (
        select(Word, up_sq.label("up_vote"), down_sq.label("down_vote"), user_vote_sq)
        .where(Word.id == word_id)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return None
    word, up, down, user_vote = row
    return word, int(up or 0), int(down or 0), user_vote


def _word_to_word_read(
    word: Word, up: int, down: int, user_vote: str | None
) -> WordRead:
    return WordRead(
        id=word.id,
        text=word.text,
        word_type=word.word_type,
        pronunciation=word.pronunciation,
        explanation=word.explanation,
        example=word.example,
        synonyms=word.synonyms or [],
        collocations=word.collocations or [],
        difficulty=word.difficulty,
        source_url=word.source_url,
        source_sentence=word.source_sentence,
        model_source=word.model_source,
        up_vote=up,
        down_vote=down,
        user_vote=user_vote if user_vote in ("up", "down") else None,
        query_count=word.query_count,
        last_queried_at=word.last_queried_at,
        created_at=word.created_at,
    )


async def _find_word_in_db(db: AsyncSession, text: str) -> Word | None:
    result = await db.execute(
        select(Word).where(func.lower(Word.text) == text.strip().lower()).limit(1)
    )
    return result.scalar_one_or_none()


async def _bump_query_count(db: AsyncSession, word_id: UUID) -> Word | None:
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
    row: Word,
    up: int,
    down: int,
    user_vote: str | None,
    *,
    cached: bool,
    db_hit: bool,
    model: str,
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
        up_vote=up,
        down_vote=down,
        user_vote=user_vote if user_vote in ("up", "down") else None,
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


async def _llm_call(text: str) -> WordResponse | SentenceResponse:
    try:
        return await call_openrouter(text)
    except OpenRouterError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# ── Routes ───────────────────────────────────────────────────────────


@router.post("/explain", response_model=ExplainResponse)
async def explain(
    req: ExplainRequest, db: DbDep, current_email: EmailOptDep
) -> ExplainResponse:
    """Route entry. Branches on word (≤2 tokens) vs sentence (>2 tokens).

    - Word path: Redis (LLM cache) → Postgres → LLM. Auto-saves to `words`.
    - Sentence path: Redis (Google Translate cache) → Google Translate. No DB write,
      no LLM, no keyword chips. See ADR 022.
    """
    if _is_wordish(req.text):
        return await _explain_word(req, db, current_email)
    return await _explain_sentence(req)


async def _explain_sentence(req: ExplainRequest) -> ExplainResponse:
    """Google Translate path — no LLM, no DB write, no keyword chips."""
    try:
        translation, was_cached = await call_google_translate(req.text)
    except GoogleTranslateError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return ExplainResponse(
        kind="sentence",
        text=req.text,
        explanation=translation,
        keywords=[],
        saved=False,
        model_source="google-translate",
        cached=was_cached,
    )


async def _explain_word(
    req: ExplainRequest, db: AsyncSession, current_email: str | None
) -> ExplainResponse:
    """Existing word lookup pipeline: Redis → Postgres → LLM, auto-save to words."""
    model = settings.openrouter_model
    key = cache_key(model, req.text)

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
                agg = await _word_with_aggregates(db, row.id, current_email)
                if agg is None:
                    raise HTTPException(500, "Failed to read back upserted word")
                _, up, down, user_vote = agg
                return _explain_response_from_row(
                    row, up, down, user_vote, cached=True, db_hit=False, model=model,
                )
        # If the legacy cache holds a sentence shape under the old key, ignore it —
        # sentence flow has moved off the LLM (ADR 022). Fall through to a fresh call.

    # Postgres second-tier cache (word path only — guaranteed wordish here)
    existing = await _find_word_in_db(db, req.text)
    if existing is not None:
        bumped = await _bump_query_count(db, existing.id)
        row = bumped or existing
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
        agg = await _word_with_aggregates(db, row.id, current_email)
        if agg is None:
            raise HTTPException(500, "Failed to read back DB-hit word")
        _, up, down, user_vote = agg
        return _explain_response_from_row(
            row, up, down, user_vote, cached=False, db_hit=True, model=model,
        )

    # Tier 3: vdict_words table (on-demand crawl if not cached)
    vdict_row = await vdict_lookup_in_db(db, req.text)
    if vdict_row is not None:
        return vdict_to_explain_response(vdict_row, cached=False, db_hit=True)

    # Tier 4: on-demand vdict.com fetch → save to vdict_words
    crawl_result = await fetch_and_parse(req.text)
    if crawl_result is not None:
        raw_html, entry = crawl_result
        vdict_row = await vdict_upsert_to_db(db, entry, raw_html)
        return vdict_to_explain_response(vdict_row, cached=False, db_hit=False)

    # Tier 5: LLM fallback — disabled by default (set USE_LLM_FALLBACK=true to re-enable)
    if not settings.use_llm_fallback:
        raise HTTPException(
            status_code=404,
            detail=f"Word not found on vdict.com: {req.text!r}",
        )

    response = await _llm_call(req.text)
    await cache_set(key, response.model_dump(mode="json"), ttl_seconds=settings.cache_ttl_seconds)

    if isinstance(response, WordResponse):
        row = await _upsert_word(
            db, response,
            source_url=req.source_url, source_sentence=None, model=model,
        )
        agg = await _word_with_aggregates(db, row.id, current_email)
        if agg is None:
            raise HTTPException(500, "Failed to read back upserted word")
        _, up, down, user_vote = agg
        return _explain_response_from_row(
            row, up, down, user_vote, cached=False, db_hit=False, model=model,
        )

    raise HTTPException(
        status_code=502,
        detail="LLM returned a sentence-shaped response for a word query",
    )


@router.post("/words/save", response_model=list[WordRead])
async def save_keywords(
    req: SaveKeywordsRequest, db: DbDep, current_email: EmailOptDep
) -> list[WordRead]:
    model = settings.openrouter_model
    saved: list[WordRead] = []
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
        agg = await _word_with_aggregates(db, row.id, current_email)
        if agg is None:
            continue
        _, up, down, user_vote = agg
        saved.append(_word_to_word_read(row, up, down, user_vote))
    return saved


@router.get("/words/today", response_model=list[WordRead])
async def words_today(db: DbDep, current_email: EmailOptDep) -> list[WordRead]:
    start, end = _today_range()
    return await _list_words(
        db,
        current_email,
        extra_filters=[Word.last_queried_at >= start, Word.last_queried_at <= end],
    )


@router.get("/words", response_model=list[WordRead])
async def words_all(
    db: DbDep, current_email: EmailOptDep, limit: int = 1000
) -> list[WordRead]:
    return await _list_words(db, current_email, limit=limit)


async def _list_words(
    db: AsyncSession,
    current_email: str | None,
    *,
    extra_filters: list | None = None,
    limit: int = 1000,
) -> list[WordRead]:
    up_sq, down_sq = _vote_aggregates_subquery()
    user_vote_sq = _user_vote_subquery(current_email)
    stmt = select(
        Word,
        up_sq.label("up_vote"),
        down_sq.label("down_vote"),
        user_vote_sq,
    )
    for f in extra_filters or []:
        stmt = stmt.where(f)
    stmt = stmt.order_by(
        (up_sq - down_sq).desc(),
        Word.last_queried_at.desc(),
    ).limit(limit)

    result = await db.execute(stmt)
    out: list[WordRead] = []
    for word, up, down, user_vote in result.all():
        out.append(_word_to_word_read(word, int(up or 0), int(down or 0), user_vote))
    return out


@router.post("/words/{word_id}/vote", response_model=WordRead)
async def vote_word(
    word_id: UUID, req: VoteRequest, db: DbDep, current_email: EmailReqDep
) -> WordRead:
    """Reddit-style vote toggle.

    - No existing row → INSERT
    - Same direction  → DELETE (unvote)
    - Opposite        → UPDATE direction
    """
    existing = await db.execute(
        select(WordVote)
        .where(WordVote.word_id == word_id)
        .where(WordVote.user_email == current_email)
        .limit(1)
    )
    row = existing.scalar_one_or_none()

    if row is None:
        # Validate the word exists (to give a clean 404 vs an FK error)
        word_exists = await db.execute(select(Word.id).where(Word.id == word_id))
        if word_exists.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Word not found")
        await db.execute(
            pg_insert(WordVote).values(
                word_id=word_id,
                user_email=current_email,
                direction=req.direction,
            )
        )
    elif row.direction == req.direction:
        await db.execute(delete(WordVote).where(WordVote.id == row.id))
    else:
        await db.execute(
            update(WordVote)
            .where(WordVote.id == row.id)
            .values(direction=req.direction, voted_at=func.now())
        )

    await db.commit()

    agg = await _word_with_aggregates(db, word_id, current_email)
    if agg is None:
        raise HTTPException(404, "Word not found")
    word, up, down, user_vote = agg
    return _word_to_word_read(word, up, down, user_vote)
