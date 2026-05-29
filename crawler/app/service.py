"""vdict.com HTTP fetch + batch DB upsert.

Separated from main.py so it can be unit-tested independently.
"""

import asyncio
import dataclasses
import logging
from urllib.parse import quote

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VdictWord
from app.parser import ParsedEntry

logger = logging.getLogger(__name__)

VDICT_BASE = "https://vdict.com"
_HEADERS = {
    "User-Agent": "vvn-crawler/1.0 (personal use; +https://github.com/qitpydev)",
    "Accept-Language": "vi,en;q=0.7",
}


def _word_url(word: str) -> str:
    return f"{VDICT_BASE}/{quote(word.strip(), safe='')},1,0,0.html"


async def fetch_html(word: str, max_retries: int = 3) -> str | None:
    """HTTP GET with exponential backoff. Returns None on 400 or exhausted retries."""
    url = _word_url(word)
    backoff = 1.0
    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=30.0) as client:
        for attempt in range(max_retries):
            try:
                res = await client.get(url)
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.warning("HTTP error %s (attempt %d): %s", url, attempt + 1, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if res.status_code == 200:
                return res.text
            if res.status_code == 400:
                return None
            if res.status_code in (429, 502, 503, 504):
                logger.warning("Status %d %s (attempt %d), backing off %.1fs",
                               res.status_code, url, attempt + 1, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            logger.warning("Status %d %s, giving up", res.status_code, url)
            return None
    return None


def _build_values(entry: ParsedEntry, raw_html: str | None) -> dict:
    return {
        "vdict_id": entry.vdict_id,
        "text": entry.text,
        "ipa": entry.ipa,
        "word_type": entry.word_type,
        "meanings": [dataclasses.asdict(dg) for dg in entry.definitions],
        "examples": [dataclasses.asdict(ep) for ep in entry.examples],
        "friendly": {
            "synonyms": entry.synonyms,
            "phrasal_verbs": [dataclasses.asdict(pv) for pv in entry.phrasal_verbs],
            "idioms": [dataclasses.asdict(id_) for id_ in entry.idioms],
        },
        "audio_url": entry.audio_url,
        "raw_html": raw_html,
    }


async def bulk_upsert_to_db(
    db: AsyncSession,
    batch: list[tuple[ParsedEntry, str | None]],
) -> int:
    """INSERT … ON CONFLICT DO UPDATE for a batch. One transaction, returns rows written."""
    for entry, raw_html in batch:
        values = _build_values(entry, raw_html)
        stmt = pg_insert(VdictWord).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["vdict_id"],
            set_={
                "text": stmt.excluded.text,
                "ipa": stmt.excluded.ipa,
                "word_type": stmt.excluded.word_type,
                "meanings": stmt.excluded.meanings,
                "friendly": stmt.excluded.friendly,
                "examples": stmt.excluded.examples,
                "audio_url": stmt.excluded.audio_url,
                "raw_html": stmt.excluded.raw_html,
            },
        )
        await db.execute(stmt)
    await db.commit()
    return len(batch)
