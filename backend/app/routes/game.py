import random
from datetime import datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.word import GameResult, Word
from app.schemas.word import GameResultRequest, GameTodayResponse, GameWordPair

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _today_range() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
    return start, end


@router.get("/game/today", response_model=GameTodayResponse, deprecated=True)
async def game_today(db: DbDep) -> GameTodayResponse:
    """DEPRECATED: matching game disabled — see ADR 019 for Spaced Repetition design."""
    start, end = _today_range()
    result = await db.execute(
        select(Word)
        .where(Word.last_queried_at >= start)
        .where(Word.last_queried_at <= end)
        .order_by(Word.last_queried_at.desc())
    )
    rows = list(result.scalars().all())
    pairs = [GameWordPair(id=w.id, word=w.text, definition=w.explanation) for w in rows]
    random.shuffle(pairs)
    return GameTodayResponse(pairs=pairs)


@router.post("/game/result", status_code=201, deprecated=True)
async def game_result(req: GameResultRequest, db: DbDep) -> dict:
    """DEPRECATED."""
    row = GameResult(
        total_words=req.total_words,
        correct=req.correct,
        duration_seconds=req.duration_seconds,
    )
    db.add(row)
    await db.commit()
    return {"ok": True}
