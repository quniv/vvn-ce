import hashlib
import logging

import httpx

from app.services.cache import get_redis

logger = logging.getLogger(__name__)

USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
TOKEN_CACHE_TTL = 60 * 5  # 5 minutes


class AuthError(Exception):
    """Raised when a Google access token cannot be verified."""


def _token_cache_key(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"auth:{digest}"


async def verify_token_get_email(access_token: str) -> str:
    """Resolve a Google OAuth access token to the user's verified email address.

    Caches `token → email` in Redis for 5 minutes to avoid hitting Google's
    userinfo endpoint on every authenticated request.

    Raises AuthError on any failure (HTTP non-200, missing email, network).
    """
    key = _token_cache_key(access_token)
    redis = get_redis()
    try:
        cached = await redis.get(key)
    except Exception as e:
        logger.warning("Redis GET failed for auth cache: %s", e)
        cached = None
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as e:
        raise AuthError(f"Google userinfo unreachable: {e}") from e

    if res.status_code != 200:
        raise AuthError(f"Google userinfo {res.status_code}: {res.text[:200]}")

    data = res.json()
    email = data.get("email")
    if not email:
        raise AuthError("userinfo response missing email field")
    if data.get("email_verified") is False:
        raise AuthError("email not verified by Google")

    try:
        await redis.set(key, email, ex=TOKEN_CACHE_TTL)
    except Exception as e:
        logger.warning("Redis SET failed for auth cache: %s", e)

    return email
