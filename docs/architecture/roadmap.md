# Roadmap

> Goal: ship a working end-to-end extension today. Phases are time-boxed for a single session.

---

## Phase 0 – Project Scaffold (1 hour)

**Goal:** Backend running, DB schema in place, health endpoint returns 200.

- [ ] `mkdir -p ~/Workspace/personal/vocab-ce/{extension,backend}`
- [ ] Backend: `cd backend && uv init && uv add fastapi uvicorn sqlalchemy asyncpg alembic psycopg2-binary python-dotenv httpx`
- [ ] Backend: Write `app/main.py` with FastAPI app + CORS middleware (allow all origins for localhost development)
- [ ] Backend: Write DB models — `Word` table and `GameResult` table using SQLAlchemy 2.x async
- [ ] Backend: Write `alembic.ini` + run `alembic init alembic` + create initial migration
- [ ] Backend: Write `Dockerfile` (base: `python:3.12-slim`, install with `uv`)
- [ ] Write `docker-compose.yml`: `api` service (FastAPI, port 8000) + `db` service (`postgres:16-alpine`, named volume, env vars)
- [ ] Create `.env` with `OPENROUTER_API_KEY=...`, `OPENROUTER_MODEL=deepseek/deepseek-chat-v3:free`, `DATABASE_URL=postgresql+asyncpg://vocab:vocab@db/vocab`
- [ ] `docker compose up -d` and verify:
  ```bash
  curl http://localhost:8000/api/health
  # expects: {"status": "ok"}
  ```

**Effort:** ~1 hour

**Risk:** asyncpg connection string must use `postgresql+asyncpg://` scheme — `postgresql://` alone will fail silently with SQLAlchemy async engine.

---

## Phase 1 – Backend API Complete (1.5 hours)

**Goal:** All API endpoints functional and tested with curl.

- [ ] `POST /api/explain` — detect type (word = no spaces, sentence = has spaces), call OpenRouter with `deepseek/deepseek-chat-v3:free` using the teacher prompt, parse structured response; auto-save to DB if word; return explanation JSON with `keywords[]` array if sentence
- [ ] OpenRouter response parser: extract `word_type`, `pronunciation`, `explanation`, `example`, and `keywords` (for sentence type)
- [ ] `POST /api/words/save` — save a list of selected keywords (from sentence flow)
- [ ] `GET /api/words` — list all saved words (support optional `date` query param filter)
- [ ] `GET /api/words/today` — words with `created_at::date = today`
- [ ] `GET /api/game/today` — today's words as `[{word, definition}]` pairs, shuffled
- [ ] `POST /api/game/result` — save `{date, score, total}` to `game_results` table
- [ ] Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`; docker-compose reads it automatically
- [ ] Test all endpoints with curl or HTTPie

**Effort:** ~1.5 hours

**Risk:** OpenRouter response format varies by model — test with a real API call early in this phase, before building the parser around assumed structure.

---

## Phase 2 – CE Scaffold + Word Flow (2 hours)

**Goal:** Select a single word on any page → popup appears with explanation → word saved to DB.

- [ ] `cd extension && pnpm create vite . --template svelte`
- [ ] Configure `vite.config.js` for multi-page CE output (content, background, options, game as separate entry points)
- [ ] Write `manifest.json` — MV3 spec:
  - `permissions`: `["storage", "activeTab", "scripting", "tabs"]`
  - `host_permissions`: `["http://localhost:8000/*"]`
  - `background.service_worker`: `"background.js"`
  - `content_scripts`: matches `["<all_urls>"]`
- [ ] `src/content/content_script.js` — listen for `mouseup`; read `window.getSelection().toString()`; if non-empty, send message to service worker; attach Svelte popup component inside a Shadow DOM root on the page
- [ ] `src/background/background.js` (service worker) — receive message; read backend URL from `chrome.storage.local` (default `http://localhost:8000`); POST to `/api/explain`; send response back to content script via `chrome.tabs.sendMessage`
- [ ] `src/popup/Popup.svelte` — word flow UI: word, pronunciation, type badge, explanation, example; close button (X); Esc key dismisses
- [ ] `pnpm build` → `extension/dist/`
- [ ] Load in Chrome: `chrome://extensions` → Enable Developer Mode → Load unpacked → select `extension/dist/`
- [ ] Test: open any webpage, select a word, confirm popup appears with explanation

**Effort:** ~2 hours

**Risk:** Shadow DOM attachment with a Svelte component requires ~20 lines of setup in the content script (create shadow root, mount Svelte component into it). MV3 service worker message passing (content script → background → content script) has a specific async pattern — use `chrome.runtime.sendMessage` from content script and `chrome.tabs.sendMessage` from background back.

---

## Phase 2b – CE Sentence Flow (1 hour)

**Goal:** Select a sentence → popup shows explanation + keyword chips → user saves chosen ones.

- [ ] Extend `Popup.svelte` — if API response contains `keywords[]`: render keyword chips row below the explanation
- [ ] Chip component: show word text + type badge; toggle selected state on click (visual: outline → filled/highlighted)
- [ ] "Save selected" button: visible when at least 1 chip is selected; POSTs selected keywords array to `POST /api/words/save`
- [ ] Success state: button text changes to "Saved ✓" for 2 seconds, then popup closes
- [ ] Test: select a sentence on any page → popup shows explanation + chips → select chips → click save → verify rows appear in DB

**Effort:** ~1 hour

**Risk:** Svelte 5 `$state` array for tracking selected chips — use a `Set` or array of selected indices; toggling membership needs to trigger a reactive re-render (replace array reference, not mutate in place with `push`).

---

## Phase 3 – Mini Game (1.5 hours)

**Goal:** End-of-day matching game for all words saved today.

- [ ] `src/options/Options.svelte` — input field for backend URL; saves to `chrome.storage.local` on submit; shows saved confirmation
- [ ] Configure toolbar icon click to open `game.html` in a new tab (`chrome.tabs.create`)
- [ ] `src/game/Game.svelte` — fetch `GET /api/game/today` on mount; handle 0-words edge case with friendly message
- [ ] Matching game UI:
  - Left column: word cards (clickable)
  - Right column: definition cards (shuffled separately, clickable)
  - Click a word, then click a definition to attempt a match
  - Correct: both cards turn green and lock (disabled)
  - Wrong: both cards flash red, reset selection after 800ms
  - All matched: show final score (X / total) + "Play again tomorrow" message
- [ ] `POST /api/game/result` when game ends
- [ ] Test: play the game with words saved during Phase 2 testing

**Effort:** ~1.5 hours

**Risk:** Matching state logic (track selected word card, selected definition card, matched pairs set) — use a single Svelte `$state` object, not ad-hoc DOM reads. Handle the edge case where `GET /api/game/today` returns an empty array.

---

## Phase 3.5 — Caching, Vietnamese Output, Voting (done)

**Goal:** Make repeat selections instant via Redis cache; write explanations in Vietnamese (~100 words); add 👍/👎 voting with vote-ordered listings.

**Note:** An earlier iteration of this phase added a model-picker UI and a daily catalog sync (APScheduler + `openrouter_models` table). Both were rolled back — see [ADR 010](adr/010-hardcode-model-no-picker.md). The model is now hardcoded via the `OPENROUTER_MODEL` env var.

**Backend (current state):**
- [x] `redis:7-alpine` service in `docker-compose.yml` (volume `vocab_redis_data`, healthcheck)
- [x] `uv add redis`
- [x] `app/services/cache.py` — async wrapper around `redis.asyncio` (`cache_get` / `cache_set`, key `explain:{model}:{sha256(text)}`, TTL 30d)
- [x] Alembic migration — add `up_vote`, `down_vote`, `model_source` columns to `words`
- [x] `app/services/openrouter.py` — Vietnamese ~100-word SYSTEM_PROMPT
- [x] `app/schemas/word.py` — `up_vote`/`down_vote`/`model_source` on `WordRead`; `VoteRequest`
- [x] `app/routes/words.py` — cache check before LLM call; record `model_source`; `POST /api/words/{id}/vote` route; listings ordered by `(up_vote - down_vote) DESC, created_at DESC`
- [x] `app/config.py` + `.env` + `.env.example` — `REDIS_URL`

**Frontend (current state):**
- [x] `extension/src/lib/types.ts` — `up_vote`/`down_vote`/`model_source`/`cached` on `ExplainResponse`; VOTE message
- [x] `extension/src/background/service-worker.ts` — handles VOTE
- [x] `extension/src/content/popup/Popup.svelte` — 👍/👎 buttons after explanation renders
- [x] `extension/src/game/Game.svelte` — no client sort change needed (backend orders by net score)

---

## Phase 4 — DB Lookup, Richer Word Card, Word Bank (today)

**Goal:** make repeat queries instant even after a cache flush by using PostgreSQL as a second-tier cache; enrich the card with synonyms / collocations / difficulty; expose all queried words in a Word Bank tab inside the game page.

**Backend**
- [ ] Alembic migration: ADD `synonyms JSONB`, `collocations JSONB`, `difficulty VARCHAR(16)`, `query_count INTEGER`, `last_queried_at TIMESTAMPTZ` to `words`; collapse existing duplicates by net-score; CREATE UNIQUE INDEX `uq_words_lower_text` ON `words (LOWER(text))`
- [ ] `app/models/word.py` — add the 5 new columns
- [ ] `app/schemas/word.py` — `KeywordItem`, `ExplainResponse`, `WordRead` gain `synonyms` / `collocations` / `difficulty` / `query_count` / `last_queried_at`; `ExplainResponse` adds `db_hit: bool`
- [ ] `app/services/openrouter.py` — SYSTEM_PROMPT requires `synonyms` / `collocations` / `difficulty`; `WordResponse` and `KeywordItem` pydantic models include them with defaults
- [ ] `app/routes/words.py` — `_is_wordish()` heuristic; cache-miss + wordish → DB SELECT by `LOWER(text)`; UPSERT on save via `INSERT ... ON CONFLICT (LOWER(text)) DO UPDATE`; bump `query_count` + `last_queried_at`; return `db_hit`
- [ ] `/api/words/save` UPSERTs each keyword (same dedupe pattern)
- [ ] All listing endpoints (`/api/words`, `/api/words/today`, `/api/game/today`) order by `(up_vote - down_vote) DESC, last_queried_at DESC`

**Frontend**
- [ ] `extension/src/lib/types.ts` — extend `KeywordItem`, `ExplainResponse`, `WordRead` with the new fields; add `db_hit?: boolean`; add `SYNC_WORDBANK` message variant
- [ ] `extension/src/background/service-worker.ts` — `syncWordBank()` writes `chrome.storage.local.wordBank`; fire-and-forget after each EXPLAIN / SAVE_KEYWORDS / VOTE; handle SYNC_WORDBANK message
- [ ] `extension/src/content/popup/Popup.svelte` — difficulty badge, synonyms chips, collocations list, "queried Nx" indicator, "from local · queried Nx" when `db_hit`
- [ ] `extension/src/game/Game.svelte` — convert to tabbed shell (Game | Word Bank); extract `GameTab.svelte`
- [ ] `extension/src/game/WordBank.svelte` — instant load from chrome.storage; SYNC_WORDBANK on mount; cards grid; filters (search, difficulty, type); sort (recent/most-queried/highest-voted/alphabetical); expand-on-click

**Effort:** ~4–6 hours

**Risk:** the migration must dedupe existing rows BEFORE creating the unique index, otherwise it fails on duplicate `LOWER(text)`. Hand-write the data step instead of relying on `--autogenerate`.

---

## Phase 5 — Look-up Gating + Popup Theming (today)

**Goal:** stop firing the LLM call on every selection; let the user explicitly click "Look up". Support light + dark themes (auto by default, manual toggle), no border, ~90% opacity background.

**Extension only — no backend changes.**

- [ ] `extension/src/content/popup/theme.ts` — `PopupTheme` type; `getStoredTheme/setStoredTheme/detectOSTheme/effectiveTheme` helpers
- [ ] `extension/src/lib/types.ts` — add `POPUP_THEME_KEY` constant
- [ ] `extension/src/content/popup/LookupButton.svelte` — small "🔍 Look up" pill, themed, dispatches `onLookup`
- [ ] `extension/src/content/content-script.ts` — refactor flow: mouseup → show LookupButton; on click → show Popup. Extract shared "mount in Shadow DOM at (x,y)" helper. Update dismissal (click outside, Esc, new selection).
- [ ] `extension/src/content/popup/Popup.svelte` — add theme state + toggle button; rewrite CSS: remove border, use `rgba` 90% opacity, add `:host(.theme-light)` / `@media (prefers-color-scheme: light)` light-mode rules across every coloured element (text, chips, vote buttons, badges, syn-chips, kw-detail, .example, .pron, etc.)

**Effort:** ~2–3 hours

**Risk:** light mode requires auditing every CSS rule in Popup.svelte (~30 rules touch colours). The Lookup button mount path duplicates current Shadow DOM logic — extract a helper rather than copy/paste.

---

## Phase 6 – K8s Migration (Future — when cluster is ready)

**Goal:** Move backend to Kubernetes; extension works with remote backend URL.

- [ ] Backend URL is already configurable via Options page (done in Phase 3) — just update the URL
- [ ] Write `k8s/` manifests:
  - `Deployment` for FastAPI (stateless, 1–2 replicas)
  - `Service` (ClusterIP + Ingress for external access)
  - `ConfigMap` for `OPENROUTER_MODEL` and other non-secret config
  - `Secret` for `OPENROUTER_API_KEY`, `DATABASE_URL`, `REDIS_URL`
- [ ] PostgreSQL: use CloudNativePG operator or managed DB (DigitalOcean Managed PostgreSQL, etc.)
- [ ] Redis: managed Redis or `bitnami/redis` Helm chart
- [ ] Migrate data: `pg_dump` from Docker volume → restore to K8s PostgreSQL
- [ ] Add `GET /api/health` as K8s liveness and readiness probe (already implemented in Phase 0)
- [ ] Add Alembic migration init container or K8s Job as pre-deploy hook
- [ ] Update Options page in extension with new backend URL (ingress hostname)

**Effort:** ~3–4 hours when K8s cluster is ready

**Risk:** Network reachability from local Chrome to K8s cluster — if cluster is not publicly exposed, use an Ingress with local DNS (`/etc/hosts`) or a VPN. The `host_permissions` in `manifest.json` must be updated to include the new backend hostname (requires rebuilding and reloading the extension).
