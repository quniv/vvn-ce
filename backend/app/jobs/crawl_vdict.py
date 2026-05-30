"""Crawl vdict.com (dict_id=1, English → Vietnamese) into the local vdict_words table.

Sitemap-driven. Polite. Resumable. Idempotent UPSERT.

Run as:
    uv run python -m app.jobs.crawl_vdict                       # full crawl
    uv run python -m app.jobs.crawl_vdict --limit 50            # first 50 only
    uv run python -m app.jobs.crawl_vdict --force               # re-crawl all (don't skip existing)
    uv run python -m app.jobs.crawl_vdict --concurrency 5       # raise concurrency

See ADR 020 for design.
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
from sqlalchemy import select

from app.db import AsyncSessionLocal, engine
from app.jobs.vdict_parser import parse_entry
from app.models.vdict_word import VdictWord
from app.services.vdict import fetch_html, upsert_to_db

logger = logging.getLogger("crawl_vdict")

SITEMAPS = [
    "https://vdict.com/sitemaps/sitemap-dict-1-1.xml",
    "https://vdict.com/sitemaps/sitemap-dict-1-2.xml",
]
USER_AGENT = "vvn-crawler/1.0 (personal use; +https://github.com/qitpydev)"
# Pattern: https://vdict.com/{word},1,0,0.html
_URL_WORD = re.compile(r"^https://vdict\.com/(.+?),1,0,0\.html$")


async def fetch_sitemap_urls(client: httpx.AsyncClient) -> list[str]:
    """Fetch both sitemaps and return all word URLs."""
    all_urls: list[str] = []
    for url in SITEMAPS:
        logger.info("Fetching sitemap: %s", url)
        res = await client.get(url)
        res.raise_for_status()
        # Parse XML cheaply with selectolax's HTML parser (XML is close enough for <loc> extraction)
        tree = XMLParser(res.text)
        locs = tree.css("loc")
        urls = [loc.text() for loc in locs if loc.text()]
        all_urls.extend(urls)
        logger.info("  %s URLs", len(urls))
    return all_urls


def parse_word_from_url(url: str) -> str | None:
    m = _URL_WORD.match(url.strip())
    if not m:
        return None
    return unquote(m.group(1))


async def already_crawled_vdict_ids(session) -> set[int]:
    result = await session.execute(select(VdictWord.vdict_id))
    return set(result.scalars().all())


async def crawl_url(
    url: str,
    session_factory,
    stats: dict,
) -> None:
    """Fetch one URL, parse, upsert. Updates `stats` dict in place."""
    word = parse_word_from_url(url)
    if word is None:
        stats["parse_fail"] += 1
        return
    html = await fetch_html(word)
    if html is None:
        stats["404"] += 1
        return
    entry = parse_entry(html)
    if entry is None or entry.vdict_id is None:
        stats["parse_fail"] += 1
        return
    async with session_factory() as session:
        await upsert_to_db(session, entry, html)
    stats["ok"] += 1


async def run(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "vi,en;q=0.7"}

    # Sitemap fetch uses a short-lived client; word fetches go via fetch_html() in the service
    async with httpx.AsyncClient(
        headers=headers, follow_redirects=True
    ) as sitemap_client:
        urls = await fetch_sitemap_urls(sitemap_client)
    logger.info("Total URLs in sitemap: %d", len(urls))

    # Filter out URLs we can't parse a word from
    urls = [u for u in urls if parse_word_from_url(u)]

    if args.limit is not None:
        urls = urls[: args.limit]
        logger.info("Limiting crawl to first %d URLs", args.limit)

    # Resumable: skip already-crawled entries by text
    if not args.force:
        async with AsyncSessionLocal() as session:
            done = await already_crawled_vdict_ids(session)
        logger.info("Already crawled: %d entries", len(done))
        if done:
            async with AsyncSessionLocal() as session:
                done_texts = await session.execute(select(VdictWord.text))
                done_text_set = {t.strip().lower() for t in done_texts.scalars().all()}
            before = len(urls)
            urls = [
                u
                for u in urls
                if (parse_word_from_url(u) or "").strip().lower() not in done_text_set
            ]
            logger.info(
                "Skipping %d already-crawled URLs; %d remain",
                before - len(urls),
                len(urls),
            )

    sem = asyncio.Semaphore(args.concurrency)
    stats = {"ok": 0, "404": 0, "parse_fail": 0}
    delay = args.delay_ms / 1000.0
    start = time.time()
    total = len(urls)

    async def worker(url: str, idx: int):
        async with sem:
            await crawl_url(url, AsyncSessionLocal, stats)
            if delay > 0:
                await asyncio.sleep(delay)
            if idx % 100 == 0 and idx > 0:
                elapsed = time.time() - start
                rate = idx / max(elapsed, 1e-6)
                eta = (total - idx) / max(rate, 1e-6)
                logger.info(
                    "Progress: %d/%d (%.1f%%) — ok=%d, 404=%d, parse_fail=%d — "
                    "%.1f req/s — ETA %.1f min",
                    idx,
                    total,
                    idx * 100.0 / total,
                    stats["ok"],
                    stats["404"],
                    stats["parse_fail"],
                    rate,
                    eta / 60,
                )

    tasks = [worker(u, i) for i, u in enumerate(urls)]
    await asyncio.gather(*tasks)

    elapsed = time.time() - start
    logger.info(
        "Crawl complete: %d URLs in %.1f min — ok=%d, 404=%d, parse_fail=%d",
        total,
        elapsed / 60,
        stats["ok"],
        stats["404"],
        stats["parse_fail"],
    )


async def main_async(args: argparse.Namespace) -> None:
    try:
        await run(args)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl vdict.com dict_id=1 into vdict_words"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only crawl the first N URLs from the sitemap (for testing)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Max concurrent HTTP requests (default 3)",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=250,
        help="Per-request delay in milliseconds (default 250)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-crawl entries that already exist in the DB",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Committed work persists.")
        sys.exit(130)


if __name__ == "__main__":
    main()
