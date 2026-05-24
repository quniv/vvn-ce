# ADR 001 — Backend (not CE) owns the OpenRouter API key and makes all LLM calls

**Status:** Accepted

---

## Context

The system needs to call OpenRouter for AI-generated vocabulary explanations. Two options were considered:

**Option A:** The Chrome Extension calls OpenRouter directly, with the API key stored in `chrome.storage.local` and read by `background.js` (service worker).

**Option B:** The Chrome Extension sends selected text to the FastAPI backend. The backend holds the API key as a server-side environment variable and makes all OpenRouter calls.

---

## Decision

**Option B** — the FastAPI backend owns the API key via the `OPENROUTER_API_KEY` environment variable (read from `.env` by Docker Compose). The Chrome Extension never has visibility into this key.

---

## Consequences

**Positive:**
- The API key never appears in extension code, `chrome.storage.local`, browser memory, or browser network logs — it exists only in the server-side environment
- The backend can add caching, rate-limiting, usage logging, and retry logic in one place without updating the extension
- The AI model can be changed (via `OPENROUTER_MODEL` env var) without publishing an extension update
- Key rotation is a single server-side operation (update `.env`, restart container)
- The extension's `manifest.json` does not need `host_permissions` for `openrouter.ai`

**Negative:**
- The FastAPI backend must be running (`localhost:8000`) for the extension to function — the extension has a hard dependency on the backend
- Adds one network hop: CE → Backend → OpenRouter (vs CE → OpenRouter directly)

**Risk:** Backend unavailability means the extension stops working entirely.

**Mitigation:** The extension's popup shows a clear "Backend offline — start Docker and retry" error message with a retry button when `POST /api/explain` fails to connect. The user is a developer who understands this dependency.
