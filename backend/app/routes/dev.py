"""Developer-only inspection routes. Mounted in main.py ONLY when settings.debug is True."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.vdict_word import VdictWord

router = APIRouter(prefix="/dev")
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/vdict/{text}")
async def lookup_vdict(text: str, db: DbDep) -> dict:
    """Return the vdict_words row matching the given headword (case-insensitive).
    Strips raw_html from the response to keep it readable.
    """
    result = await db.execute(
        select(VdictWord).where(func.lower(VdictWord.text) == text.strip().lower())
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No vdict entry for {text!r}")
    return {
        "vdict_id": row.vdict_id,
        "text": row.text,
        "ipa": row.ipa,
        "word_type": row.word_type,
        "meanings": row.meanings,
        "friendly": row.friendly,
        "examples": row.examples,
        "crawled_at": row.crawled_at.isoformat(),
    }


@router.get("/vdict")
async def stats(db: DbDep) -> dict:
    """Crawler progress summary."""
    total = await db.execute(select(func.count(VdictWord.vdict_id)))
    return {"total_words": total.scalar() or 0}
