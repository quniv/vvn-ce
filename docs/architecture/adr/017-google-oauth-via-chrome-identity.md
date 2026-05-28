# ADR-017: Google OAuth via `chrome.identity` for Vote Attribution

## Status
Accepted

## Context

Voting now needs to be attributed to a specific user (see [ADR-016](016-per-user-vote-table.md)). The vote endpoint requires an authenticated email. Three options were considered:

1. **`chrome.identity.getAuthToken`** — Chrome's built-in OAuth flow tied to the user's Chrome-profile Google account. Returns an OAuth access token.
2. **`chrome.identity.launchWebAuthFlow`** — Opens a popup window with any OAuth provider (Google, GitHub, etc.). More flexible but more code.
3. **Email + password / magic link** — Build our own auth from scratch. Way out of scope.

Option 1 is the cleanest for a Chrome Extension that needs Google sign-in only. The user's existing Chrome profile account is reused — no separate login dance.

For backend verification, two paths:

1. **Verify the JWT signature locally** using Google's JWKS (`https://www.googleapis.com/oauth2/v3/certs`). Fast, no per-request external call, but requires a `google-auth` library and JWKS cache management.
2. **Call Google's userinfo endpoint** with the access token. Simple HTTP call, no crypto, but adds latency (mitigatable with caching).

For a personal-scale tool, latency is not a concern. Option 2 + Redis caching is dramatically simpler.

## Decision

### Frontend (extension)

- `manifest.json` declares the `identity` permission and an `oauth2` section with `scopes: ["openid", "email", "profile"]`.
- The service worker has a helper:
  ```ts
  async function getAccessToken(interactive: boolean): Promise<string | null> {
    return new Promise(resolve => {
      chrome.identity.getAuthToken({ interactive }, t => resolve(t ?? null))
    })
  }
  ```
- VOTE: `getAccessToken(true)` — interactive, prompts sign-in if needed
- EXPLAIN / SYNC_WORDBANK / SAVE_KEYWORDS: `getAccessToken(false)` — silent, returns null if not signed in (listings still work anonymously)
- The token is attached as `Authorization: Bearer <token>` to backend requests

### Backend

- New service `app/services/google_auth.py:verify_token_get_email(token)`:
  1. Compute cache key `auth:{sha256(token)}`
  2. `cache_get` → on hit, return the cached email
  3. On miss: `GET https://openidconnect.googleapis.com/v1/userinfo` with `Authorization: Bearer <token>` — Google returns `{email, sub, name, picture, ...}`
  4. `cache_set` with TTL 5 min and return the email
  5. On Google 401: raise `HTTPException(401, "Invalid auth token")`

- New FastAPI dependencies in `app/routes/auth_deps.py`:
  - `current_user_email(authorization=Header(None))` — returns email or `None` (silent for anonymous listings)
  - `require_user_email(...)` — same but raises 401 if no email (used by `POST /vote`)

### Setup

One-time setup, documented in README:

1. Build and load the extension unpacked in `chrome://extensions`
2. Copy the extension's **Application ID** (the long hex string in chrome://extensions Details)
3. Google Cloud Console → APIs & Services → Credentials → Create credentials → **OAuth client ID** → Application type **Chrome Extension**
4. Paste the Application ID into the "Application ID" field
5. Copy the resulting Client ID (`xxxxx.apps.googleusercontent.com`) into `extension/manifest.json` under `oauth2.client_id`
6. Reload the extension

## Consequences

**Positive:**
- Zero password handling, zero credential storage on our side.
- The user's Chrome-profile account is reused — no extra account to remember.
- Backend code is tiny (one HTTP call, no JWT crypto).
- Caching keeps the user-perceived latency at ~0 ms for successive votes.

**Negative / trade-offs:**
- Adds a 5-min cache window where a revoked Google token would still appear valid. Acceptable for a personal-scale tool; for stricter scenarios drop the TTL or verify locally.
- We trust Google's userinfo response (over HTTPS). We don't validate the JWT signature locally — an attacker who could MITM Google traffic could spoof. Not realistic for our threat model.
- The `oauth2.client_id` must be present in `manifest.json` (it's a public value; not a secret).

**Risks:**
- **Google rate-limits userinfo** (~150 req/sec). Far above our usage. Cache makes it a non-issue anyway.
- **Token expiration mid-session**. `chrome.identity` handles refresh automatically when interactive.
- **`chrome.identity.getAuthToken` works only when the user is signed into Chrome with a Google account.** If the user is not signed into Chrome, the interactive flow shows the standard Google sign-in. The non-interactive flow returns null.

## Notes

We deliberately use the **access_token** (not the ID token) because chrome.identity makes the access token easy and the userinfo endpoint accepts it directly. We could request an ID token via `launchWebAuthFlow` if local JWT verification ever becomes important.

If usage grows beyond personal scale, the recommended upgrade is:
- Switch to local JWT verification with the `google-auth` Python library
- Cache JWKS for 24 h
- Drop the userinfo HTTP call entirely
