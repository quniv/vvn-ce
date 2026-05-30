"""Translate sentences via Google Translate's unofficial public endpoint.

`translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=...`
returns a nested JSON array. The translation segments are at `response[0][i][0]`.

We deliberately don't use a paid Cloud Translation API key — this endpoint
serves the public Translate web widget and is free for low-volume use.
"""

import hashlib
import logging
from typing import Any

import httpx

from app.services.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

ENDPOINT = "https://translate.googleapis.com/translate_a/single"
CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days
CACHE_PREFIX = "gt"

# Identify ourselves; values mirror what a normal browser visit to translate.google.com sends
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "vi,en;q=0.8",
    "Referer": "https://translate.google.com/",
}


class GoogleTranslateError(Exception):
    """Raised when the unofficial endpoint returns a non-200 or unparseable shape."""


def _cache_key(text: str, source: str, target: str) -> str:
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()
    return f"{CACHE_PREFIX}:{source}-{target}:{digest}"


def _extract_translation(payload: Any) -> str:
    """Parse the nested-array response into a single translated string.

    Shape:
      [
        [
          ["<vi segment 1>", "<en segment 1>", ...],
          ["<vi segment 2>", "<en segment 2>", ...],
          ...
        ],
        null,
        "en",
        ...
      ]
    Segments are joined with a space.
    """
    if not isinstance(payload, list) or not payload:
        raise GoogleTranslateError(
            f"Unexpected payload top-level: {type(payload).__name__}"
        )
    segments = payload[0]
    if not isinstance(segments, list) or not segments:
        raise GoogleTranslateError("Payload[0] is missing or empty")
    parts: list[str] = []
    for seg in segments:
        if isinstance(seg, list) and seg and isinstance(seg[0], str):
            parts.append(seg[0])
    if not parts:
        raise GoogleTranslateError("No translation segments found in payload")
    return "".join(parts).strip()


async def translate(
    text: str, *, source: str = "en", target: str = "vi"
) -> tuple[str, bool]:
    """Translate `text` from `source` to `target`. Returns (translation, was_cached).

    Cache hits return immediately. On miss, hits Google's endpoint and writes the
    result to Redis with a 30-day TTL.
    """
    if not text or not text.strip():
        raise GoogleTranslateError("Empty text")

    key = _cache_key(text, source, target)
    cached = await cache_get(key)
    if cached is not None:
        # cache_get returns the deserialized value; we stored a dict for compatibility
        if isinstance(cached, dict) and "translation" in cached:
            return cached["translation"], True
        # Defensive: handle the case where we stored a bare string in an earlier iteration
        if isinstance(cached, str):
            return cached, True

    params = {
        "client": "gtx",
        "sl": source,
        "tl": target,
        "dt": "t",
        "q": text,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=DEFAULT_HEADERS) as client:
            res = await client.get(ENDPOINT, params=params)
    except httpx.HTTPError as e:
        raise GoogleTranslateError(f"Google Translate request failed: {e}") from e

    if res.status_code != 200:
        raise GoogleTranslateError(
            f"Google Translate returned HTTP {res.status_code}: {res.text[:200]}"
        )

    try:
        payload = res.json()
    except Exception as e:
        raise GoogleTranslateError(f"Google Translate returned non-JSON: {e}") from e

    translation = _extract_translation(payload)
    await cache_set(key, {"translation": translation}, ttl_seconds=CACHE_TTL_SECONDS)
    return translation, False
