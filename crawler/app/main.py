"""vdict.com bulk crawler — k8s CronJob entrypoint.

Fetches all English-Vietnamese word pages from the vdict.com sitemaps and
upserts structured data into the shared vdict_words Postgres table.

Usage (local):
    CRAWLER_DB_URL=postgresql+asyncpg://vocab:vocab@localhost:5432/vocab \\
        python -m app.main [--limit N] [--concurrency N] [--delay-ms N]

CLI flags override env-var defaults (CRAWLER_* prefix). See app/config.py.
"""

import argparse
import asyncio
import logging
import re
import sys
import time
from urllib.parse import unquote

import httpx
from selectolax.parser import HTMLParser as XMLParser
from sqlalchemy import func, select

from app.config import settings
from app.db import AsyncSessionLocal, engine
from app.models import VdictWord
from app.parser import parse_entry
from app.service import bulk_upsert_to_db, fetch_html

logger = logging.getLogger("vdict-crawler")

SITEMAPS = [
    "https://vdict.com/sitemaps/sitemap-dict-1-1.xml",
    "https://vdict.com/sitemaps/sitemap-dict-1-2.xml",
]
_URL_WORD = re.compile(r"^https://vdict\.com/(.+?),1,0,0\.html$")
_SITEMAP_HEADERS = {
    "User-Agent": "vocab-ce-crawler/1.0 (personal use; +https://github.com/qitpydev)",
    "Accept-Language": "vi,en;q=0.7",
}


async def fetch_sitemap_urls() -> list[str]:
    all_urls: list[str] = []
    async with httpx.AsyncClient(headers=_SITEMAP_HEADERS, follow_redirects=True, timeout=30.0) as client:
        for url in SITEMAPS:
            logger.info("Fetching sitemap: %s", url)
            res = await client.get(url)
            res.raise_for_status()
            tree = XMLParser(res.text)
            urls = [loc.text() for loc in tree.css("loc") if loc.text()]
            all_urls.extend(urls)
            logger.info("  %d URLs", len(urls))
    return all_urls


def _parse_word(url: str) -> str | None:
    m = _URL_WORD.match(url.strip())
    return unquote(m.group(1)) if m else None


async def run(args: argparse.Namespace) -> None:
    # Configure logging
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=handlers,
        force=True,
    )

    urls = await fetch_sitemap_urls()
    logger.info("Total sitemap URLs: %d", len(urls))
    urls = [u for u in urls if _parse_word(u)]

    if args.limit is not None:
        urls = urls[: args.limit]
        logger.info("Limiting to first %d URLs", args.limit)

    # Resume: skip already-crawled words (case-insensitive match)
    if not args.force:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(func.lower(VdictWord.text)))
            done = {t for t in result.scalars().all()}
        logger.info("Already in DB: %d words", len(done))
        before = len(urls)
        urls = [u for u in urls if (_parse_word(u) or "").strip().lower() not in done]
        logger.info("Skipping %d already-crawled; %d remain", before - len(urls), len(urls))

    sem = asyncio.Semaphore(args.concurrency)
    stats = {"ok": 0, "not_found": 0, "parse_fail": 0}
    delay = args.delay_ms / 1000.0
    no_raw_html: bool = args.no_raw_html
    batch_size: int = args.batch_size
    start = time.time()
    total = len(urls)

    async def fetch_one(url: str) -> tuple | None:
        async with sem:
            word = _parse_word(url)
            if not word:
                stats["parse_fail"] += 1
                return None
            html = await fetch_html(word)
            if delay > 0:
                await asyncio.sleep(delay)
            if html is None:
                stats["not_found"] += 1
                return None
            entry = parse_entry(html)
            if entry is None or entry.vdict_id is None:
                stats["parse_fail"] += 1
                return None
            return entry, (None if no_raw_html else html)

    async with AsyncSessionLocal() as session:
        for chunk_start in range(0, total, batch_size):
            chunk = urls[chunk_start: chunk_start + batch_size]
            raw = await asyncio.gather(*[fetch_one(u) for u in chunk], return_exceptions=True)

            batch = []
            for r in raw:
                if isinstance(r, Exception):
                    logger.warning("Unexpected worker error: %s", r)
                    stats["parse_fail"] += 1
                elif r is not None:
                    batch.append(r)
                    stats["ok"] += 1

            if batch:
                await bulk_upsert_to_db(session, batch)

            done = min(chunk_start + batch_size, total)
            elapsed = time.time() - start
            rate = done / max(elapsed, 1e-6)
            eta_min = (total - done) / max(rate, 1e-6) / 60
            logger.info(
                "Progress: %d/%d (%.1f%%) — ok=%d, not_found=%d, parse_fail=%d"
                " — %.1f req/s — ETA %.1f min",
                done, total, done * 100.0 / max(total, 1),
                stats["ok"], stats["not_found"], stats["parse_fail"],
                rate, eta_min,
            )

    elapsed = time.time() - start
    logger.info(
        "Done: %d URLs in %.1f min — ok=%d, not_found=%d, parse_fail=%d",
        total, elapsed / 60,
        stats["ok"], stats["not_found"], stats["parse_fail"],
    )


async def _main_async(args: argparse.Namespace) -> None:
    try:
        await run(args)
    finally:
        await engine.dispose()


def main() -> None:
    p = argparse.ArgumentParser(description="Crawl all vdict.com English-Vietnamese words")
    p.add_argument("--concurrency", type=int, default=settings.concurrency,
                   help=f"Max concurrent fetches (default {settings.concurrency})")
    p.add_argument("--delay-ms", type=int, default=settings.delay_ms,
                   help=f"Per-request delay in ms (default {settings.delay_ms})")
    p.add_argument("--batch-size", type=int, default=settings.batch_size,
                   help=f"DB commit every N words (default {settings.batch_size})")
    p.add_argument("--no-raw-html", action="store_true", default=settings.no_raw_html,
                   help="Skip storing raw HTML (saves ~8 GB)")
    p.add_argument("--force", action="store_true", default=settings.force,
                   help="Re-crawl words already in DB")
    p.add_argument("--limit", type=int, default=settings.limit,
                   help="Crawl only the first N sitemap URLs (for testing)")
    p.add_argument("--log-file", default=settings.log_file,
                   help="Also write log to this file path")
    args = p.parse_args()

    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        logger.info("Interrupted. Committed batches persist in DB.")
        sys.exit(130)


if __name__ == "__main__":
    main()
