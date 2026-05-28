# Architecture Overview — Vocab Chrome Extension

## Executive Summary

A personal English vocabulary learning tool for a single Vietnamese developer, consisting of a Chrome Extension (Manifest V3, built with Svelte 5 + Vite) and a FastAPI backend running on localhost via Docker Compose. When the user highlights text on any webpage, a floating popup appears with an AI-generated explanation; the extension never calls OpenRouter directly — all LLM calls are made server-side by the FastAPI backend, which holds the API key exclusively. The LLM model is hardcoded in the backend via the `OPENROUTER_MODEL` env var (default `z-ai/glm-4.5-air:free`) — see [ADR 010](adr/010-hardcode-model-no-picker.md). Explanations are cached in Redis keyed on `(text, model)`, so repeated selections are instant and free. For single words, the backend auto-saves the result to PostgreSQL immediately; for sentences, the backend returns a list of keyword/phrasal verb chips that the user explicitly selects and saves. At end of day, a matching game lets the user review every word saved that session.

---

## System Architecture

```mermaid
graph TB
    subgraph Browser ["Browser (Chrome)"]
        CS["content_script.js<br/>text selection listener"]
        LB["Look-up button<br/>Svelte component"]
        SW["background.js<br/>service worker"]
        UI["Popup Overlay<br/>Svelte component (themed)"]
        GAME["Game Page<br/>Svelte page"]
        OPT["Options Page<br/>Svelte page"]
    end

    subgraph Backend ["Backend (localhost:8000)"]
        API["FastAPI<br/>REST API"]
        DB["PostgreSQL 16<br/>words + word_votes + vdict_words (seed, ~80k)"]
        REDIS["Redis 7<br/>cache: text+model → explanation<br/>+ auth: token → email (5m)"]
    end

    subgraph LLM ["External"]
        OR["OpenRouter API<br/>API key + model: server-side only"]
        MODELS["Configured model<br/>deepseek/deepseek-v4-flash (env var)"]
        GAUTH["Google userinfo<br/>verifies OAuth access_token → email"]
    end

    subgraph Storage ["chrome.storage.local"]
        WB["wordBank<br/>(mirror of /api/words)"]
        OPTS["backendUrl"]
        THEME["popupTheme<br/>(dark | light | undefined)"]
    end

    CS -- "mouseup → selection" --> LB
    LB -- "user clicks → text" --> SW
    SW -- "POST /api/explain {text}" --> API
    API -- "1. Redis get" --> REDIS
    API -- "2. if word & cache miss: SELECT LOWER(text)" --> DB
    API -- "3. if no DB row: call OpenRouter" --> OR
    OR --> MODELS
    MODELS -- "explanation JSON" --> OR
    OR -- "response" --> API
    API -- "4. cache set (TTL 30d) + UPSERT words" --> REDIS
    API -- "explanation + keywords" --> SW
    SW -- "render response" --> UI
    SW -- "fire-and-forget GET /api/words" --> API
    SW -- "write" --> WB
    SW -- "POST /api/words/{id}/vote<br/>Bearer access_token" --> API
    API -- "verify token → email" --> GAUTH
    API -- "cache token→email (5m)" --> REDIS
    GAME -- "GET /api/words (Word Bank tab)" --> API
    GAME -- "read cached" --> WB
    OPT -- "saves backendUrl" --> OPTS
```

---

## Component Breakdown

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| content_script.js | JS injected into page | Detects text selection on `mouseup`; mounts a floating **"🔍 Look up" button** in a Shadow DOM near the selection; on click, mounts the full Popup Overlay (also Shadow DOM). Manages dismissal (click outside, Esc, new selection). Reads `popupTheme` to apply dark/light class. |
| Look-up button | Svelte (Shadow DOM) | Small pill button rendered next to a text selection. Click triggers the existing EXPLAIN flow. Respects theme (auto / dark / light). |
| background.js (service worker) | MV3 Service Worker | Relays EXPLAIN/SAVE/VOTE messages between content script and backend; reads `backendUrl` from `chrome.storage.local`. **Obtains OAuth access tokens via `chrome.identity.getAuthToken`** — interactive for VOTE (prompts sign-in), non-interactive for listing reads. Attaches `Authorization: Bearer` header to backend calls. |
| Popup Overlay | Svelte component (in-page) | Shows **multi-paragraph** Vietnamese explanation, keyword chips for sentence flow, Save and 👍/👎 vote buttons; attached to page via Shadow DOM. **Themed** (dark / light, auto-detect by default, manual toggle in header, persisted in `chrome.storage.local.popupTheme`); no border; ~90% opacity background. Vote button "active" state reflects the **current user's** vote (from `user_vote` field), not aggregate counts. |
| Options Page | Svelte page | User sets `backendUrl`; that's it. The LLM model is configured server-side. |
| Game Page | Svelte page | Defaults to the **Word Bank** tab (all queried words with filters/search/sort). The Game tab is **disabled** in this CR — replaced by a "Spaced Repetition coming soon" placeholder linking to [ADR 019](adr/019-spaced-repetition-design.md). Word Bank reads chrome.storage.local first, then refreshes from `GET /api/words`. |
| FastAPI Backend | Python + FastAPI | Calls OpenRouter with server-side API key + hardcoded model; manages words/votes; serves game data; owns all LLM communication |
| Redis 7 | Docker container | Cache for LLM responses keyed on `explain:{model}:{sha256(text)}`, TTL 30 days |
| PostgreSQL 16 | Docker container | Persistent store: `words` (text, explanation, pronunciation, example, `model_source`, `up_vote`, `down_vote`), `game_results` |
| OpenRouter | External API | Routes LLM requests to the configured model (env var `OPENROUTER_MODEL`, default `z-ai/glm-4.5-air:free`) |

---

## Data Flows

### Single Word Flow

```
1. User selects a single word on any webpage
2. mouseup fires → content_script.js reads window.getSelection()
2a. content_script mounts a small "🔍 Look up" button (Shadow DOM) at the selection's bottom-left
2b. User clicks the button → button is removed, popup-mount path begins
3. content_script sends message to background.js (service worker)
4. background.js reads backendUrl from chrome.storage.local
5. background.js POSTs { "text": "word", "source_url": "..." }
   to POST /api/explain
6. Backend computes cache key = sha256(env-var model + ":" + lowercased text)
7. Backend checks Redis (GET explain:<model>:<hash>):
     - **HIT**  → returns cached explanation immediately (<100ms); also UPSERTs `words` row to bump query_count
     - **MISS** → continue
8. Backend treats the input as "wordish" if `len(text.split()) <= 2`. If wordish:
     - SELECT FROM words WHERE LOWER(text) = LOWER($1) LIMIT 1
     - **DB hit** → UPDATE query_count+1, last_queried_at=now(); hydrate Redis; return row's data with `db_hit=true`
     - **DB miss** → continue to LLM
9. On true miss, backend calls OpenRouter with the env-var model and Vietnamese-explanation prompt
10. Backend writes the response into Redis (TTL 30d)
11. Backend UPSERTs the word into PostgreSQL (INSERT ... ON CONFLICT (LOWER(text)) DO UPDATE) with the new fields (synonyms, collocations, difficulty), `model_source`, `query_count=1`. **Vote columns are no longer on the word row** — they live in a separate `word_votes` table.
12. Backend returns explanation JSON (word id, model_source, aggregated up/down votes via JOIN, **user_vote** for the current authenticated user (or null), synonyms, collocations, difficulty, query_count, cached flag, db_hit flag)
13. Popup Overlay renders **multi-paragraph** Vietnamese explanation (~100 words across 2–4 paragraphs), word_type + difficulty badges, IPA, English example, synonyms chips, collocations list
14. User reads, optionally clicks 👍 or 👎 — see [Vote Flow](#vote-flow) below
15. Service worker fire-and-forget refreshes chrome.storage.local.wordBank from `GET /api/words`
16. User closes popup with X or Esc
```

### Sentence Flow

```
1. User selects a sentence (≥3 tokens) on any webpage
2. mouseup fires → content_script.js reads window.getSelection()
2a. content_script mounts a "🔍 Look up" button (Shadow DOM) at the selection's bottom-left
2b. User clicks the button → button removed, popup mount begins
3. content_script sends message to background.js
4. background.js POSTs { "text": "sentence", "source_url": "..." } to POST /api/explain
5. Backend detects sentence (>2 tokens), uses Google Translate path:
     a. Compute cache key = "gt:en-vi:" + sha256(text.lower())
     b. Redis check → on hit, return cached translation (<100ms)
     c. On miss: GET translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=<text>
     d. Parse response[0][i][0] segments, join, save to Redis (TTL 30d)
6. Backend returns { kind: "sentence", text: <original>, explanation: <vi translation>,
                     keywords: [], model_source: "google-translate", cached: <bool> }
7. Popup shows the original English sentence + the Vietnamese translation. No keyword chips.
8. To save a specific word from the sentence, user re-highlights just that word (word flow)
```

### Word Bank Flow (new)

```
1. User clicks the extension icon → game page opens with two tabs: Game | Word Bank
2. Word Bank tab on mount:
     - Reads chrome.storage.local.wordBank → renders cards immediately (instant load, works offline)
     - Sends SYNC_WORDBANK message to service worker
3. Service worker:
     - GET /api/words?limit=1000 from backend
     - Writes the array to chrome.storage.local.wordBank with a fresh wordBankSyncedAt timestamp
     - Returns the array to the tab
4. Tab replaces the rendered list with the fresh data
5. User can filter (search text, by difficulty, by word_type), sort (recent / most-queried / highest-voted / alphabetical), or click a card to expand details (synonyms chips, collocations list, example sentence)
6. Service worker also fire-and-forget syncs after every successful EXPLAIN / SAVE_KEYWORDS / VOTE, so the cache stays warm without the user opening the tab
```

### Vote Flow

```
1. After an explanation renders in the popup, user clicks 👍 or 👎
2. Popup sends VOTE message to service worker with { wordId, direction }
3. Service worker calls `chrome.identity.getAuthToken({ interactive: true })` to obtain a Google OAuth access token
   - If the user has not granted permission yet, Chrome shows a sign-in prompt
   - If the user cancels, VOTE returns `{ ok: false, error: 'Sign-in cancelled' }` and the popup shows an inline retry
4. Service worker POSTs `/api/words/{wordId}/vote` with `{ direction: "up" | "down" }` and `Authorization: Bearer <access_token>`
5. Backend verifies the token by calling Google's `https://openidconnect.googleapis.com/v1/userinfo`
   - On success, Google returns the user's email; backend caches `token → email` in Redis (TTL 5 min)
   - Future votes from the same token hit the cache (no Google round-trip)
6. Backend looks up an existing row in `word_votes` for `(word_id, user_email)`:
   - No row → INSERT new vote
   - Existing same direction → DELETE row (Reddit-style "unvote")
   - Existing opposite direction → UPDATE row's direction
7. Backend returns the updated WordRead (computed aggregates + `user_vote` for this caller)
8. Popup updates the vote counts and the active button highlight (`user_vote === 'up'` / `'down'` / `null`)
9. Listings (`/api/words`, `/api/words/today`) compute the same aggregates via LEFT JOIN to `word_votes`; ordering is `(up - down) DESC, last_queried_at DESC`
```

---

## Key Architectural Decisions

**API key is server-side only.** The `OPENROUTER_API_KEY` environment variable lives in the backend `.env` file and is read by Docker Compose. It never appears in the extension code, `chrome.storage.local`, or any browser context. See [ADR 001](adr/001-backend-owns-api-key.md).

**Svelte 5 + Vite for the CE.** Svelte compiles to plain JS at build time — no runtime overhead in the extension bundle. Scoped component styles combined with Shadow DOM prevent host-page CSS from leaking into the popup overlay. See [ADR 002](adr/002-svelte-for-ce.md).

**Differentiated save flow by input type.** Words are low-noise and always worth saving; sentences contain many words and the user should curate. Auto-saving sentence keywords would fill the DB with already-known words. See [ADR 003](adr/003-word-vs-sentence-save-flow.md).

**PostgreSQL over SQLite.** The system is designed for Kubernetes migration from day one. PostgreSQL in Docker is a direct lift-and-shift to a K8s StatefulSet or CloudNativePG operator. See [ADR 004](adr/004-postgresql-over-sqlite.md).

**Model is hardcoded in the backend.** The `OPENROUTER_MODEL` env var (default `z-ai/glm-4.5-air:free`) is the single source of truth. The extension does not send a `model` field. Earlier ADRs 006 (catalog sync job) and 007 (per-request model) were rolled back; see [ADR 010](adr/010-hardcode-model-no-picker.md).

**Redis-backed explanation cache.** LLM responses are cached at `explain:{model}:{sha256(text)}` with a 30-day TTL. The model id is constant now but still in the key, so a future model change creates a fresh namespace automatically. See [ADR 005](adr/005-redis-for-llm-cache.md).

**Vietnamese explanations (~100 words, multi-paragraph).** The system prompt instructs the model to write the `explanation` field in Vietnamese, targeting 50–150 words split into **2–4 short paragraphs** separated by blank lines. `word_type`, `pronunciation` (IPA), and `example` (English sentence) remain in English/IPA. See [ADR 008](adr/008-vietnamese-explanations.md) (original) + [ADR 018](adr/018-multi-paragraph-explanations.md) (paragraphs).

**Per-user voting via Google OAuth.** ADR 009's integer counters were dropped. Votes now live in a `word_votes(word_id, user_email, direction)` table with a unique constraint on `(word_id, user_email)`. Clicking the same direction twice "unvotes"; clicking the opposite direction switches. The extension uses `chrome.identity.getAuthToken` to obtain an OAuth access token; the backend verifies it via Google's userinfo endpoint and caches `token → email` in Redis (TTL 5 min). See [ADR 016](adr/016-per-user-vote-table.md) + [ADR 017](adr/017-google-oauth-via-chrome-identity.md).

**Matching game disabled — Spaced Repetition is the next CR.** The Game tab in `game.html` is now a placeholder. `/api/game/*` endpoints are deprecated. The full SM-2 Spaced Repetition design is documented in [ADR 019](adr/019-spaced-repetition-design.md) for the follow-up implementation.

**vdict.com seeded as a free local dictionary (Phase 8a).** A new `vdict_words` table holds ~80k crawled entries from vdict.com's English→Vietnamese dictionary (dict_id=1). The data is **populated but not yet consumed** by the word-flow lookup. A future CR (Phase 8b) will wire the lookup priority `Redis → vdict_words → words → LLM`, making most word lookups free and instant. See [ADR 020](adr/020-vdict-seed-dictionary.md) for crawler design.

**Google Translate replaces LLM for sentence flow (Phase 8b-prelude — current).** Sentence selections now route to Google's unofficial `translate.googleapis.com/translate_a/single` endpoint instead of the LLM. Latency drops from 10–20s to <1s. Keyword chips are removed — to save a specific word from a sentence, highlight just that word individually (word flow). See [ADR 022](adr/022-google-translate-for-sentences.md). The previously-planned local-n-gram approach ([ADR 021](adr/021-local-ngram-sentence-flow.md)) is no longer needed for this purpose, since GT provides the sentence translation directly.
