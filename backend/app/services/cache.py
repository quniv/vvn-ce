import hashlib
import json
import logging
from typing import Any

from redis.asyncio import Redis, from_url

from app.config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def cache_key(model: str, text: str) -> str:
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()
    return f"explain:{model}:{digest}"


async def cache_get(key: str) -> dict[str, Any] | None:
    try:
        raw = await get_redis().get(key)
    except Exception as e:
        logger.warning("Redis GET failed for %s: %s", key, e)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Cached value at %s was not valid JSON; ignoring", key)
        return None


async def cache_set(key: str, value: dict[str, Any], ttl_seconds: int = 60 * 60 * 24 * 30) -> None:
    try:
        await get_redis().set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as e:
        logger.warning("Redis SET failed for %s: %s", key, e)
