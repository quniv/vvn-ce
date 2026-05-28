# Tech Stack

## 1. CE Framework: Svelte 5 + Vite

**Chosen: Svelte 5 with Vite multi-page build**

Svelte compiles components to plain JavaScript at build time — there is no Svelte runtime shipped with the extension. This results in the smallest possible bundle size among major frameworks, which matters in a Chrome Extension where every KB contributes to load time and review surface. Svelte 5's runes API (`$state`, `$derived`) provides fine-grained reactivity with syntax close to plain HTML. Scoped styles per component prevent leakage into host pages (combined with Shadow DOM for the popup overlay).

| Option | Pros | Cons |
|--------|------|------|
| **Svelte 5 + Vite (chosen)** | Compiles away — zero runtime overhead; smallest bundle of major frameworks; CSS scoped per component; reactive without virtual DOM; simple syntax close to HTML | Fewer CE-specific tutorials than React; Svelte 5 runes API is new |
| React 18 + Vite | Most CE tutorials use React; large community and examples; familiar to React developers | ~40KB runtime always bundled; virtual DOM overhead unnecessary for small UIs |
| Vanilla JS | Zero build step; load unpacked instantly; full MV3 compatibility | Manual DOM manipulation becomes painful as UI grows; no reactivity; no component isolation |

**Build output:** `extension/dist/` — load this folder in Chrome via Developer Mode → Load unpacked.

**Multi-page Vite config entry points:**
- `src/content/content_script.js` — injected into every page
- `src/background/background.js` — MV3 service worker
- `src/popup/popup.html` — in-page Svelte component (attached via Shadow DOM)
- `src/options/options.html` — options page
- `src/game/game.html` — game page (opens in new tab)

---

## 2. AI Model: hardcoded `OPENROUTER_MODEL` env var (default `z-ai/glm-4.5-air:free`)

**Chosen: hardcode the model in the backend via the `OPENROUTER_MODEL` env var.**

The backend reads `OPENROUTER_MODEL` from `.env` once at startup. Every `POST /api/explain` uses this model. The extension does not send a `model` field. To change the model, edit `.env` and run `docker compose up -d --force-recreate api` (`restart` does NOT re-read `env_file`).

A previous design had a model dropdown in the Options page (ADR-007) and a daily sync job (ADR-006) to populate it. Both were rolled back as over-engineering for a single-user personal tool — see [ADR 010](adr/010-hardcode-model-no-picker.md).

GLM-4.5 Air was the most reliable free model at launch; it is a "thinking" model so responses take ~5–20 seconds, but quality is good and the upstream provider has been stable.

**System prompt (Vietnamese ~100-word target):**

The prompt instructs the model to write the `explanation` field in Vietnamese, targeting roughly 100 words (50–150 acceptable range). `word_type`, `pronunciation` (IPA), and `example` (English sentence) remain in English/IPA since those are study targets, not study aids. See [ADR 008](adr/008-vietnamese-explanations.md).

**Candidate free models if you want to switch (edit `.env`):**

| Model | ID | Speed | Notes |
|-------|----|-------|-------|
| **GLM-4.5 Air** | `z-ai/glm-4.5-air:free` | ~5–20s | Current default — reliable upstream, excellent multilingual |
| DeepSeek V4 Flash | `deepseek/deepseek-v4-flash:free` | ~1–3s | Fastest free option when available; goes in/out of rate-limit |
| Llama 3.3 70B | `meta-llama/llama-3.3-70b-instruct:free` | ~2–5s | Large model, good quality |
| Gemma 4 31B | `google/gemma-4-31b-it:free` | ~2–4s | Google's open model |

| Option | Pros | Cons |
|--------|------|------|
| **Hardcoded env-var model (chosen)** | Single source of truth; smaller codebase; one fewer route, table, and background job; Options page is dead simple | Switching models requires `.env` edit + container recreate |
| Per-request from CE dropdown | Switching is one click; no restart | Adds complexity (route, table, sync job, UI); user almost always wants the same model anyway |
| Auto-rotate on upstream errors | Resilient to free-tier rate limits | Complex retry logic; can mask real misconfiguration |

---

## 3. Backend: FastAPI (Python 3.12) with uv

**Chosen: FastAPI + uv**

FastAPI is async-native, which is important for proxying LLM streaming responses in the future without blocking. It auto-generates OpenAPI docs at `/docs` — useful for debugging endpoints during development. The user has existing FastAPI experience, removing the framework learning curve.

**Package management: always use `uv`. Never use `pip` or `venv` directly.**

```bash
# Init and add dependencies
uv init backend
cd backend
uv add fastapi uvicorn sqlalchemy asyncpg alembic psycopg2-binary python-dotenv httpx

# Run the server
uv run uvicorn app.main:app --reload --port 8000
```

| Option | Pros | Cons |
|--------|------|------|
| **FastAPI + uv (chosen)** | Async-native; auto OpenAPI docs; Pydantic validation; user has experience; uv is the fastest Python package manager | Slightly more setup than Flask |
| Express.js (Node) | Good async story; large ecosystem; familiar if JS-heavy team | Different language stack; no uv equivalent for dependency speed |
| Rust (Axum) | Maximum throughput | Bottleneck is OpenRouter latency (~1–3s), not Python overhead; adds significant complexity for a personal tool; rejected |

---

## 4. Database: PostgreSQL 16

**Chosen: PostgreSQL 16 in Docker**

PostgreSQL is the right choice even for a single-user personal tool when Kubernetes migration is on the roadmap. A SQLite database would need to be converted (not just moved) when migrating to K8s. PostgreSQL in Docker is a direct lift-and-shift: `pg_dump` → restore to a K8s StatefulSet or CloudNativePG operator. Proper `TIMESTAMPTZ` columns and native UUID support are bonuses.

**DB Schema (words table):**

```sql
CREATE TABLE words (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    text            TEXT NOT NULL,
    word_type       TEXT,
    pronunciation   TEXT,
    explanation     TEXT NOT NULL,             -- Vietnamese, ~100 words, 2-4 paragraphs separated by \n\n
    example         TEXT,                       -- English example sentence
    synonyms        JSONB NOT NULL DEFAULT '[]',
    collocations    JSONB NOT NULL DEFAULT '[]',
    difficulty      VARCHAR(16),                -- beginner | intermediate | advanced
    source_url      TEXT,
    source_sentence TEXT,
    model_source    TEXT,                       -- LLM that produced this row
    query_count     INTEGER NOT NULL DEFAULT 1,
    last_queried_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at     TIMESTAMPTZ
);

CREATE TABLE word_votes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    word_id     UUID NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    user_email  VARCHAR(320) NOT NULL,
    direction   VARCHAR(4) NOT NULL CHECK (direction IN ('up', 'down')),
    voted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_word_votes_word_user ON word_votes (word_id, user_email);
CREATE INDEX ix_word_votes_word_id ON word_votes (word_id);

-- One row per (case-insensitive) word — enforced by:
CREATE UNIQUE INDEX uq_words_lower_text ON words (LOWER(text));

-- Listings order: aggregate (up - down) DESC, last_queried_at DESC
--   up_vote   = COUNT(word_votes WHERE direction='up')
--   down_vote = COUNT(word_votes WHERE direction='down')
--   user_vote = the current authenticated user's vote, or NULL
```

_(There is no `openrouter_models` table any more — see [ADR 010](adr/010-hardcode-model-no-picker.md).)_

| Option | Pros | Cons |
|--------|------|------|
| **PostgreSQL 16 (chosen)** | K8s-portable (StatefulSet / CloudNativePG); UUID support; timezone-aware timestamps; future multi-user capable | Docker must be running; more setup than SQLite |
| SQLite | Zero config; file-based; no Docker dependency | Not K8s-portable — requires schema rewrite for migration; concurrency limits; no managed cloud equivalent |
| MongoDB | Flexible schema; good Docker support | Structured vocabulary data benefits from relational schema; overkill for this use case |

---

## 5. ORM: SQLAlchemy 2.x + Alembic

**Chosen: SQLAlchemy 2.x (async) + Alembic**

SQLAlchemy 2.x with the `asyncpg` driver provides fully async database access, matching FastAPI's async model. Alembic migrations are essential for safe K8s deploys — schema changes are applied as versioned, reversible migration scripts rather than manual `ALTER TABLE` commands.

**Key patterns:**
- Use `create_async_engine` and `AsyncSession` (not the sync equivalents)
- Connection string: `postgresql+asyncpg://user:password@host/dbname`
- Alembic `env.py` must use `run_migrations_online` with the async engine

| Option | Pros | Cons |
|--------|------|------|
| **SQLAlchemy 2 + Alembic (chosen)** | Async support with asyncpg; type-safe models; mature migration tooling; industry standard | Verbose model definitions compared to lighter ORMs |
| Tortoise ORM | Clean async API; Django-like syntax | Smaller ecosystem; less documentation |
| Raw asyncpg | Maximum control; minimal overhead | No schema migration story; manual query building scales poorly |

---

## 6. Containerization: Docker Compose → Kubernetes

**Current: Docker Compose**

```yaml
# docker-compose.yml (structure)
services:
  api:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [db]

  db:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_USER: vocab
      POSTGRES_PASSWORD: vocab
      POSTGRES_DB: vocab

volumes:
  pgdata:
```

**K8s migration path (Phase 4):**
- FastAPI `api` service → K8s `Deployment` (stateless, any number of replicas)
- PostgreSQL `db` service → K8s `StatefulSet` (CloudNativePG operator recommended) or managed DB
- `Secret` for `OPENROUTER_API_KEY` and `DATABASE_URL`
- `ConfigMap` for `OPENROUTER_MODEL` and other non-secret config
- No application code changes required — only environment variable wiring

**Design constraint:** the API must be stateless from day one (no in-memory state, all state in DB). This is already the case with FastAPI + PostgreSQL.

| Option | Pros | Cons |
|--------|------|------|
| **Docker Compose (chosen for now)** | One command; matches existing Docker skills; trivial local setup | Not HA; fine for personal tool |
| Kubernetes (now) | Production-ready from day 0 | Massive overhead for a 1-user personal tool; migrate when cluster is ready |
| Bare Python + system PostgreSQL | No Docker dependency | Environment drift; no portability; no isolation |

---

## 7. CE Build: Vite + @sveltejs/vite-plugin-svelte

**Chosen: Vite with Svelte plugin, multi-page configuration**

Vite handles Svelte compilation and bundles multiple entry points (content script, service worker, options, game) as separate output files. The `manifest.json` references the compiled output files in `dist/`.

```js
// vite.config.js (structure)
import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  plugins: [svelte()],
  build: {
    rollupOptions: {
      input: {
        content: 'src/content/content_script.js',
        background: 'src/background/background.js',
        options: 'src/options/options.html',
        game: 'src/game/game.html',
      },
      output: {
        entryFileNames: '[name].js',
      }
    }
  }
})
```

**Install dependencies:**
```bash
cd extension
pnpm create vite . --template svelte
pnpm add -D @sveltejs/vite-plugin-svelte
```

**Load in Chrome:** `chrome://extensions` → Enable Developer Mode → Load unpacked → select `extension/dist/`

### UI: Look-up gate + Shadow DOM theming

The popup is no longer auto-mounted on every selection. The content script mounts a tiny **"🔍 Look up" button** in a Shadow DOM host next to the selection bounding box on `mouseup`; the full Popup mounts only after the user clicks the button. This prevents incidental LLM calls and DB rows for non-vocabulary text selections (copy/paste, reading habits). See [ADR 014](adr/014-lookup-button-gate.md).

Both the Look-up button and the Popup are themed (dark / light):

- **Default = auto-detect** via `@media (prefers-color-scheme: light)` inside Shadow DOM CSS
- **Manual override** via a toggle (🌙 / ☀️) in the Popup header — persisted to `chrome.storage.local.popupTheme` (`'dark' | 'light' | undefined`)
- **No border** on the card; background is `rgba(...)` at ~90% opacity for visual separation
- Shared helpers live in `extension/src/content/popup/theme.ts` and are read by both components on mount

See [ADR 015](adr/015-popup-theming.md).

---

## 8. Caching: Redis 7-alpine + Postgres second tier

**Chosen: Redis 7-alpine as a third Docker service (`vocab-redis`), with PostgreSQL serving as a second-tier cache for word lookups.**

LLM explanations are cached at `explain:{model}:{sha256(text.strip().lower())}` with a 30-day TTL. The cache key includes the model id, so switching models gives a separate namespace and no flush is needed when the user changes the model. Cache hits return in <100ms vs. 2–20s for an OpenRouter call.

**Lookup order for "wordish" inputs** (`len(text.split()) <= 2`): Redis → PostgreSQL → LLM. For sentence inputs (>2 tokens), the path is entirely different: Redis (at `gt:en-vi:{hash}`) → Google Translate → cache + return. No DB, no LLM. See [ADR 011](adr/011-db-as-second-tier-cache.md) for the word path and [ADR 022](adr/022-google-translate-for-sentences.md) for the sentence path.

**Pattern:** cache-aside.
1. Receive `POST /api/explain { text }`
2. `cache_get(explain:{model}:{sha256(text)})` — Redis hit returns in ~15ms
3. On Redis miss, if `_is_wordish(text)`: `SELECT * FROM words WHERE LOWER(text) = LOWER($1)` — DB hit returns in ~5ms, also hydrates Redis and bumps `query_count`
4. On both misses: call OpenRouter, then `cache_set(...)` with `EX 2592000` (30d) and UPSERT into `words`

Storing the cache key on the LLM input + model (not on the saved `Word` row) means:
- Multiple selections of the same word/sentence share one cached response across all users (we only have one).
- The `words` table still grows per-selection — votes are separate from cache.

| Option | Pros | Cons |
|--------|------|------|
| **Redis 7-alpine (chosen)** | In-memory speed; native TTL; K8s-portable (managed Redis or operator); standard cache pattern | One more service to run; ~30MB RAM overhead in Docker |
| PostgreSQL cache table | No new service; reuses existing DB | Slower than Redis; manual TTL expiry; mixes cache concerns with persistent data |
| In-memory Python dict (LRU) | Zero infrastructure | Lost on container restart; cannot share across replicas in K8s |

**Connection:** `redis://redis:6379/0` (Docker), `redis://localhost:6379/0` (host runs).

---

## 9. Word Card Structure (LLM contract)

The LLM returns explanations as strict JSON. The contract (popped out below) is the single source of truth — see also [ADR 012](adr/012-richer-card-structure.md).

**Single word response:**

```json
{
  "kind": "word",
  "text": "tenacious",
  "word_type": "adj",
  "pronunciation": "/təˈneɪ.ʃəs/",
  "explanation": "Vietnamese explanation, ~100 words…",
  "example": "She was tenacious in her pursuit of justice.",
  "synonyms":     ["persistent", "determined", "steadfast", "resolute"],
  "collocations": ["tenacious grip", "tenacious memory", "tenacious defender"],
  "difficulty":   "intermediate"
}
```

**Sentence response — same fields per keyword:**

```json
{
  "kind": "sentence",
  "text": "She tenaciously pursued her goal.",
  "explanation": "Vietnamese sentence explanation…",
  "keywords": [
    {
      "text": "tenaciously",
      "word_type": "adv",
      "pronunciation": "/təˈneɪ.ʃəs.li/",
      "explanation": "Vietnamese keyword explanation…",
      "example": "He tenaciously held onto the rope.",
      "synonyms":     ["persistently", "doggedly", "stubbornly"],
      "collocations": ["fight tenaciously", "hold on tenaciously"],
      "difficulty":   "advanced"
    }
  ]
}
```

**Field contract:**
- `synonyms`: list of 3–5 single-word English synonyms. May be empty for rare words.
- `collocations`: list of 2–5 common multi-word phrases using the headword. May be empty.
- `difficulty`: exactly one of `"beginner"`, `"intermediate"`, `"advanced"`. Required.

Older rows created before this contract have `synonyms`/`collocations` as `[]` and `difficulty` as `NULL`; the popup hides empty sections gracefully (see [ADR 012](adr/012-richer-card-structure.md)).

---

## 10. Word Bank — `chrome.storage.local` mirror

The Word Bank tab (inside the game page) displays every word the user has queried. It reads from `chrome.storage.local.wordBank` first (instant, offline-friendly) and refreshes from `GET /api/words` in the background. The service worker fire-and-forget triggers a sync after every successful EXPLAIN / SAVE_KEYWORDS / VOTE response, so opening the tab usually shows fresh data immediately. See [ADR 013](adr/013-word-bank-chrome-storage-cache.md).

```
chrome.storage.local schema:
  backendUrl:           string
  wordBank:             WordRead[]            // mirror of /api/words?limit=1000
  wordBankSyncedAt:     ISO-8601 string
```

Quota considerations: `chrome.storage.local` has a 5 MB limit. A `WordRead` row averages ~400 bytes, so ~12,500 words fit comfortably.

---

## 11. Words endpoint ordering & per-user votes

Votes are stored in a separate `word_votes(word_id, user_email, direction)` table with `UNIQUE (word_id, user_email)`. Listings compute aggregates via LEFT JOIN:

```sql
SELECT w.*,
  (SELECT COUNT(*) FROM word_votes v WHERE v.word_id = w.id AND v.direction = 'up')   AS up_vote,
  (SELECT COUNT(*) FROM word_votes v WHERE v.word_id = w.id AND v.direction = 'down') AS down_vote,
  (SELECT v.direction FROM word_votes v WHERE v.word_id = w.id AND v.user_email = :current_email LIMIT 1) AS user_vote
FROM words w
ORDER BY (up_vote - down_vote) DESC, last_queried_at DESC;
```

`current_email` is set by the `current_user_email` FastAPI dependency, which reads `Authorization: Bearer <token>` and verifies it against Google's userinfo endpoint (cached in Redis 5 min).

Voting endpoint requires authentication:

```
POST /api/words/{id}/vote
  Headers: Authorization: Bearer <google_access_token>
  Body:    { direction: "up" | "down" }
```

Toggle behaviour: clicking the same direction "unvotes" (DELETE the row); clicking the opposite switches the direction. Each click is one HTTP round-trip and the response includes fresh aggregates + `user_vote` for the caller.

See [ADR 016](adr/016-per-user-vote-table.md).

---

## 12. Auth: Google OAuth via `chrome.identity`

The extension uses Chrome's built-in identity API to obtain an OAuth access token signed by Google. No user-managed credentials, no password handling, no JWT validation — Google does the auth and we trust their userinfo response.

**Flow:**

```
1. Service worker calls chrome.identity.getAuthToken({ interactive: true/false, scopes: ['openid','email','profile'] })
2. Chrome returns an OAuth access_token (short-lived, ~1 hour)
3. Service worker includes the token in Authorization: Bearer header for backend calls
4. Backend's current_user_email dependency:
     a. cache_get("auth:" + sha256(token))   →  hit returns email instantly
     b. cache miss: GET https://openidconnect.googleapis.com/v1/userinfo with the token → {email, sub, name, ...}
     c. cache_set the result with TTL 5 min
5. The email becomes the per-user identifier for word_votes
```

**`manifest.json` requirements:**

```json
{
  "permissions": ["identity", "storage", "activeTab"],
  "oauth2": {
    "client_id": "<your-client-id>.apps.googleusercontent.com",
    "scopes": ["openid", "email", "profile"]
  }
}
```

**Setup steps** (one-time per developer): Google Cloud Console → Credentials → Create OAuth Client ID → Application type **Chrome Extension** → paste the extension's public key (from `chrome://extensions` → Details on the unpacked extension). Then paste the resulting client ID into `manifest.json`.

**Security trade-offs:**

| | Pros | Cons |
|---|---|---|
| **Verify via userinfo (chosen)** | Simple, no Google client libs, no JWT crypto | Adds latency (mitigated by 5min Redis cache); we trust Google's TLS |
| Verify JWT locally with Google's JWKS | No external call per request | Need `google-auth` lib; JWKS refresh; more code |
| Trust frontend-sent email | Trivial | Anyone can spoof — unacceptable |

See [ADR 017](adr/017-google-oauth-via-chrome-identity.md).

---

## 13. Seed dictionary: vdict.com crawl

A new read-only `vdict_words` table holds ~80k entries crawled from vdict.com's English → Vietnamese dictionary (`dict_id=1`). Phase 8a (current CR) only populates the table; Phase 8b will wire it into `/api/explain` as the primary lookup path before the LLM.

**Schema:**

```sql
CREATE TABLE vdict_words (
    vdict_id     INTEGER PRIMARY KEY,    -- vdict's internal word_id (from data-track-props)
    text         VARCHAR(512) NOT NULL,
    ipa          VARCHAR(256),
    word_type    VARCHAR(64),             -- first POS or NULL (one word may have many POS)
    meanings     JSONB NOT NULL DEFAULT '[]',  -- academic: [{"pos":"danh từ","items":["...","..."]}, ...]
    friendly     JSONB NOT NULL DEFAULT '[]',  -- friendly: richer paragraph-style content
    examples     JSONB NOT NULL DEFAULT '[]',  -- pulled from <li class="example"> in the friendly block
    raw_html     TEXT,                    -- preserved so the parser can be re-run without re-fetching
    crawled_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_vdict_words_lower_text ON vdict_words (LOWER(text));
```

**Crawler entry point:** `backend/app/jobs/crawl_vdict.py` — standalone async script, runnable as `python -m app.jobs.crawl_vdict`. Sitemap-driven, resumable, polite (3 concurrent, 250ms delay), idempotent UPSERT.

**Source URLs (sitemaps):**
- `https://vdict.com/sitemaps/sitemap-dict-1-1.xml` (50k entries)
- `https://vdict.com/sitemaps/sitemap-dict-1-2.xml` (29.9k entries)

**Responsible-crawling rules:** identify in User-Agent, default ≤12 req/s peak, back off on 429/5xx, don't redistribute the data publicly. robots.txt and llms.txt both allow this.

**Dev probe endpoint:** `GET /api/dev/vdict/{text}` — gated by `settings.debug`, returns the row (raw_html stripped) by `LOWER(text)`. For verifying parser quality.

See [ADR 020](adr/020-vdict-seed-dictionary.md) for full crawler design and [ADR 021](adr/021-local-ngram-sentence-flow.md) for the previously-planned n-gram sentence flow (now obsoleted by ADR 022).

---

## 14. Sentence translation: Google Translate (unofficial)

Sentences (>2 tokens) skip the LLM entirely. The backend calls `https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=<text>` and returns the Vietnamese translation as the `explanation` field. No keyword chips, no DB write.

**Cache:** Redis key `gt:en-vi:{sha256(text.strip().lower())}`, TTL 30 days. Same Redis instance, namespaced separately from LLM responses.

**No authentication.** The `client=gtx` query identifies as the public web Translate widget. Polite User-Agent and Accept-Language headers; standard low request volume.

**Response shape:** nested arrays. Parser extracts `response[0][i][0]` for each translation segment and joins them.

See [ADR 022](adr/022-google-translate-for-sentences.md).
