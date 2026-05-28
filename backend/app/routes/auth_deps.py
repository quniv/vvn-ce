"""FastAPI dependencies for resolving the current authenticated user from
the `Authorization: Bearer <google_access_token>` header.
"""

from fastapi import Header, HTTPException

from app.services.google_auth import AuthError, verify_token_get_email


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


async def current_user_email(authorization: str | None = Header(default=None)) -> str | None:
    """Returns the verified email if a valid Bearer token is present, or None.

    Used by endpoints that work both anonymously and authenticated (e.g. listings
    enrich the response with the user's own vote when authenticated).
    """
    token = _extract_bearer(authorization)
    if not token:
        return None
    try:
        return await verify_token_get_email(token)
    except AuthError:
        # Treat malformed/expired tokens as anonymous — let the caller decide.
        return None


async def require_user_email(authorization: str | None = Header(default=None)) -> str:
    """Returns the verified email or raises 401.

    Used by endpoints that mutate per-user state (votes).
    """
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return await verify_token_get_email(token)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
