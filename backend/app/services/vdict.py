"""Single-word vdict.com lookup service.

Shared by the on-demand route (`/api/explain`) and the batch crawler
(`app/jobs/crawl_vdict.py`). Pure async — no CLI, no argparse here.

URL pattern: https://vdict.com/{word},1,0,0.html
Audio pattern: https://audio.vdict.com/1/{vdict_id}.mp3
"""

import asyncio
import dataclasses
import logging
from urllib.parse import quote

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.vdict_parser import ParsedEntry, parse_entry
from app.models.vdict_word import VdictWord
from app.schemas.word import ExplainResponse

logger = logging.getLogger(__name__)

VDICT_BASE = "https://vdict.com"
USER_AGENT = "vocab-ce-crawler/1.0 (personal use; +https://github.com/qitpydev)"
_HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "vi,en;q=0.7"}


def _word_url(word: str) -> str:
    return f"{VDICT_BASE}/{quote(word.strip(), safe='')},1,0,0.html"


async def fetch_html(word: str, max_retries: int = 3) -> str | None:
    """HTTP GET with exponential backoff. Returns None on 400 (no entry) or exhausted retries."""
    url = _word_url(word)
    backoff = 1.0
    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=30.0) as client:
        for attempt in range(max_retries):
            try:
                res = await client.get(url)
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.warning("HTTP error fetching %s (attempt %d): %s", url, attempt + 1, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if res.status_code == 200:
                return res.text
            if res.status_code == 400:
                return None
            if res.status_code in (429, 502, 503, 504):
                logger.warning("Status %d for %s (attempt %d), backing off %.1fs",
                               res.status_code, url, attempt + 1, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            logger.warning("Status %d for %s, giving up", res.status_code, url)
            return None
    return None


async def fetch_and_parse(word: str) -> tuple[str, ParsedEntry] | None:
    """Fetch and parse a single word from vdict.com.

    Returns (raw_html, entry) or None if the word isn't on vdict.
    """
    html = await fetch_html(word)
    if html is None:
        return None
    entry = parse_entry(html)
    if entry is None or entry.vdict_id is None:
        logger.warning("vdict: parse returned no entry for word=%r", word)
        return None
    return html, entry


async def lookup_in_db(db: AsyncSession, word: str) -> VdictWord | None:
    """Case-insensitive lookup in vdict_words."""
    result = await db.execute(
        select(VdictWord)
        .where(func.lower(VdictWord.text) == word.strip().lower())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def upsert_to_db(db: AsyncSession, entry: ParsedEntry, raw_html: str) -> VdictWord:
    """INSERT … ON CONFLICT (vdict_id) DO UPDATE. Idempotent."""
    values = {
        "vdict_id": entry.vdict_id,
        "text": entry.text,
        "ipa": entry.ipa,
        "word_type": entry.word_type,
        # meanings: [{pos, items: [{vi, description}]}]
        "meanings": [dataclasses.asdict(dg) for dg in entry.definitions],
        # examples: [{en, vi}]
        "examples": [dataclasses.asdict(ep) for ep in entry.examples],
        # friendly: {synonyms, phrasal_verbs, idioms}
        "friendly": {
            "synonyms": entry.synonyms,
            "phrasal_verbs": [dataclasses.asdict(pv) for pv in entry.phrasal_verbs],
            "idioms": [dataclasses.asdict(id_) for id_ in entry.idioms],
        },
        "audio_url": entry.audio_url,
        "raw_html": raw_html,
    }
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
    ).returning(VdictWord)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


def vdict_to_explain_response(vw: VdictWord, *, cached: bool, db_hit: bool) -> ExplainResponse:
    """Convert a VdictWord row to an ExplainResponse for the popup."""
    # meanings: [{pos, items: [{vi, description}]}]
    lines: list[str] = []
    for section in (vw.meanings or []):
        pos = section.get("pos", "")
        if pos:
            lines.append(pos)
        for item in section.get("items", []):
            vi = item.get("vi", "")
            desc = item.get("description", "")
            if desc:
                lines.append(f"• {vi}: {desc}")
            elif vi:
                lines.append(f"• {vi}")
    explanation = "\n".join(lines) if lines else "(no definition available)"

    # examples: [{en, vi}]
    raw_examples: list[dict] = vw.examples or []
    example = raw_examples[0].get("en") if raw_examples else None

    # friendly: {synonyms, phrasal_verbs, idioms}
    friendly: dict = vw.friendly if isinstance(vw.friendly, dict) else {}
    synonyms: list[str] = friendly.get("synonyms", [])

    # collocations = phrasal_verbs + idioms as "phrase: vi" strings
    collocations: list[str] = []
    for pv in friendly.get("phrasal_verbs", []):
        phrase = pv.get("phrase", "")
        vi = pv.get("vi", "")
        if phrase and vi:
            collocations.append(f"{phrase}: {vi}")
    for id_ in friendly.get("idioms", []):
        phrase = id_.get("phrase", "")
        vi = id_.get("vi", "")
        if phrase and vi:
            collocations.append(f"{phrase}: {vi}")

    # vdict_examples: all bilingual pairs for the popup examples block
    vdict_examples = [{"en": e.get("en", ""), "vi": e.get("vi", "")} for e in raw_examples]

    return ExplainResponse(
        kind="word",
        text=vw.text,
        word_type=vw.word_type,
        pronunciation=vw.ipa,
        explanation=explanation,
        example=example,
        synonyms=synonyms,
        collocations=collocations,
        difficulty=None,
        keywords=[],
        saved=False,
        saved_id=None,
        model_source="vdict",
        audio_url=vw.audio_url,
        vdict_examples=vdict_examples,
        cached=cached,
        db_hit=db_hit,
    )
