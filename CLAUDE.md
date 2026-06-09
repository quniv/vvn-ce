# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal Chrome Extension + FastAPI backend for English vocabulary learning. Single Vietnamese user. The extension shows a floating "Look up" button when text is selected on any webpage; clicking it opens a popup with a Vietnamese explanation, synonyms, collocations, bilingual examples, difficulty level, and 👍/👎 voting. All looked-up words live in PostgreSQL and are mirrored to `chrome.storage.local` as a browsable Word Bank.

## Stack

| Layer | Technology |
|---|---|
| Extension | Manifest V3, Svelte 5 + Vite, TypeScript |
| Popup overlay | Shadow DOM (style isolation from host pages), dark/light theming |
| Backend | FastAPI (Python 3.14), `uv` for deps |
| Database | PostgreSQL 16 |
| Cache | Redis 7-alpine |
| Dictionary | vdict.com (~80k English-Vietnamese words, crawled on-demand + bulk) |
| LLM | OpenRouter → `deepseek/deepseek-v4-flash` (disabled by default, `USE_LLM_FALLBACK=true` to enable) |
| Orchestration | Docker Compose (local), K8s migration on roadmap |

## Common commands

```bash
# Backend
cd backend
uv sync                                       # install deps
uv run uvicorn app.main:app --reload          # local dev (without Docker)

# Alembic (run from backend/, against local DB)
DATABASE_URL="postgresql+asyncpg://vocab:vocab@localhost:5432/vocab" \
OPENROUTER_API_KEY="" \
uv run alembic revision --autogenerate -m "<msg>"

DATABASE_URL="postgresql+asyncpg://vocab:vocab@localhost:5432/vocab" \
OPENROUTER_API_KEY="" \
uv run alembic upgrade head

# vdict on-demand crawl (from backend/)
uv run python -m app.jobs.crawl_vdict --limit 50      # test: first 50 URLs
uv run python -m app.jobs.crawl_vdict                  # full bulk crawl (legacy, pre-crawler app)

# Extension
cd extension
pnpm install
pnpm build              # builds dist/ (load unpacked in chrome://extensions)
pnpm check              # svelte-check + TypeScript
pnpm build:content      # rebuild content-script IIFE only (faster iteration)

# Crawler (standalone app)
cd crawler
CRAWLER_DB_URL=postgresql+asyncpg://vocab:vocab@localhost:5432/vocab \
  uv run python -m app.main --limit 100       # sanity run: first 100 words
CRAWLER_DB_URL=postgresql+asyncpg://vocab:vocab@localhost:5432/vocab \
  uv run python -m app.main                   # full bulk crawl (~80k words, ~2h)

# Full stack (Docker Compose)
docker compose up -d                                                           # boot db + redis + api
docker compose up -d --force-recreate api                                      # apply .env / code changes
docker compose up -d --force-recreate --renew-anon-volumes --build api        # after uv add (renew venv volume)
docker compose exec api alembic upgrade head                                   # apply migrations inside container
docker compose logs -f api                                                     # tail backend logs
```

## Project layout

```
vvn-ce/
├── backend/                    # FastAPI + SQLAlchemy + Redis + OpenRouter proxy
│   ├── app/
│   │   ├── main.py             # FastAPI app + lifespan + router registration
│   │   ├── config.py           # pydantic-settings reads .env
│   │   ├── db.py               # async engine, AsyncSession dependency
│   │   ├── models/             # SQLAlchemy ORM (word.py, vote.py, vdict_word.py)
│   │   ├── schemas/word.py     # Pydantic request/response shapes
│   │   ├── routes/words.py     # /api/explain, /api/words, /api/words/{id}/vote, /api/dev/vdict
│   │   ├── services/
│   │   │   ├── cache.py        # Redis wrapper, cache key format
│   │   │   ├── openrouter.py   # SYSTEM_PROMPT + httpx call
│   │   │   ├── vdict.py        # single-word vdict lookup + on-demand crawl + DB upsert
│   │   │   └── google_translate.py  # sentence-only path (no LLM, no DB)
│   │   └── jobs/
│   │       ├── crawl_vdict.py  # sitemap crawler (legacy runner; shares service layer)
│   │       └── vdict_parser.py # pure HTML parser for vdict.com pages
│   ├── alembic/                # migrations (apply via docker compose exec api alembic upgrade head)
│   ├── pyproject.toml
│   └── .env                    # DATABASE_URL, OPENROUTER_API_KEY, REDIS_URL, OPENROUTER_MODEL, DEBUG
├── extension/                  # MV3 Chrome Extension
│   ├── src/
│   │   ├── content/
│   │   │   ├── content-script.ts        # mouseup handler → mount LookupButton + Popup (Shadow DOM)
│   │   │   └── popup/
│   │   │       ├── Popup.svelte         # explanation card (word type, IPA, audio, examples, voting)
│   │   │       ├── LookupButton.svelte  # floating pill, 50% opacity, top-right of selection
│   │   │       └── theme.ts             # dark/light helpers + chrome.storage persistence
│   │   ├── background/service-worker.ts # EXPLAIN/SAVE/VOTE/SYNC_WORDBANK message relay
│   │   ├── options/Options.svelte        # backend URL config
│   │   ├── game/
│   │   │   └── WordBank.svelte          # cards grid + filters + sort (GameTab.svelte is deprecated)
│   │   └── lib/types.ts                 # shared TS types + storage key constants
│   ├── vite.config.ts              # main build (HTML pages + service-worker → ES modules)
│   └── vite.content.config.ts      # separate IIFE build for content-script (no ES imports)
├── crawler/                    # Standalone bulk crawler — k8s CronJob target
│   ├── app/
│   │   ├── config.py           # Settings via CRAWLER_* env vars (pydantic-settings)
│   │   ├── db.py               # async SQLAlchemy engine (no FastAPI dep)
│   │   ├── models.py           # VdictWord mirror (self-contained, no backend import)
│   │   ├── parser.py           # vdict HTML parser (copy of backend/app/jobs/vdict_parser.py)
│   │   ├── service.py          # fetch_html() + bulk_upsert_to_db() (batch commits)
│   │   └── main.py             # CLI entrypoint: sitemap → filter-already-crawled → async crawl loop
│   ├── k8s/
│   │   ├── cronjob.yaml        # weekly k8s CronJob (Sun 02:00 UTC, concurrencyPolicy=Forbid)
│   │   └── secret.yaml.tpl     # DB URL secret template
│   └── Dockerfile
└── docker-compose.yml          # db + redis + api
```

## 5-tier lookup pipeline

`/api/explain` resolves a word or sentence through these tiers in order:

```
POST /api/explain {text}
  1. Redis cache         → hit: return immediately (cached: true)
  2. words table         → hit: bump query_count, hydrate Redis, return (db_hit: true)
  3. vdict_words table   → hit: return structured Vietnamese data (db_hit: true)
  4. on-demand vdict crawl → fetch vdict.com, parse, upsert to vdict_words, return
  5. LLM fallback        → disabled by default (USE_LLM_FALLBACK=true to enable)
     → raises 404 if word not found on vdict.com and LLM is off
```

**Sentence path** (detected when input is > ~3 words): Google Translate only. Skips DB, vdict, LLM. No voting, no keyword chips, no persistence. ExplainResponse.kind = "sentence".

## Hard conventions

- **Always `uv` for Python.** Never `pip install`, never `python -m venv`. Commands: `uv sync`, `uv add`, `uv run`, `uv lock`.
- **`docker compose restart` does NOT re-read `env_file`.** After editing `backend/.env`, use `docker compose up -d --force-recreate api`. After `uv add`, also pass `--renew-anon-volumes --build`.
- **Two-file Vite build.** Content script ships as a single IIFE (`vite.content.config.ts`, `inlineDynamicImports: true`). ES modules are not allowed in content scripts. HTML pages + service-worker use the main `vite.config.ts`.
- **Shadow DOM is non-negotiable** for any UI mounted into host pages. Without it, host CSS will break the popup on any styled site.
- **Backend owns the OpenRouter API key.** The extension never sees it. Model is `OPENROUTER_MODEL` env var — no user-facing model picker.
- **`words` table is deduplicated on `LOWER(text)`** via `uq_words_lower_text` unique index. Always use `INSERT … ON CONFLICT (LOWER(text)) DO UPDATE` (see `_upsert_word` in `backend/app/routes/words.py`).
- **Crawler is self-contained.** `crawler/` imports nothing from `backend/`. `models.py` and `parser.py` are explicit mirrors — keep them in sync manually when the schema changes.

## DB tables at a glance

| Table | Purpose |
|---|---|
| `words` | Deduped vocabulary (LOWER(text) unique). Stores LLM or vdict explanations. Has vote counts via joined `word_votes`. |
| `word_votes` | Reddit-style toggle votes. Unique `(word_id, user_email)`. Toggle: same dir → DELETE, opposite → UPDATE. |
| `vdict_words` | Read-only vdict.com seed data. `vdict_id` PK (not autoincrement). `meanings` JSONB `[{pos, items:[{vi,description}]}]`, `examples` JSONB `[{en,vi}]`, `friendly` JSONB `{synonyms, phrasal_verbs, idioms}`. |

## Popup behavior

- **Default dimensions**: 380×380px (width × height)
- **Min-height constraint**: 350px prevents popup from shrinking below this when resizing
- **Min-width constraint**: 280px (set in resize handler)
- **Scrolling**: `.card-body` has `overflow-y: auto` — scrollbar appears automatically when content exceeds visible area
- **Resizing**: Drag handle (⤡) at bottom-right corner. Horizontal drag affects width only, vertical drag affects height only (independent axes)
- **First load**: Popup opens at 380px height; if content is shorter, scrollbar doesn't appear; if content is longer, scrollbar enables scrolling

## Common pitfalls

- **"Cannot read properties of undefined (reading 'sendMessage')"** in the extension popup → stale content script. **Refresh the webpage (F5)** after reloading the extension.
- **Alembic migration fails on `LOWER(text)` unique index** → collapse existing duplicates first. See `c98963b230da_richer_word_card_and_dedupe.py` for the CTE + DELETE pattern.
- **`docker compose restart` silently ignores `.env` changes.** Use `--force-recreate` instead.
- **`chrome.storage.local.wordBank` can drift** from the backend after vote/save if `syncWordBank()` fails silently. Word Bank tab has a manual "↻ refresh" button.
- **Bulk crawl disk space**: running the crawler with `--no-raw-html` (the default) saves ~8 GB. Without it, `raw_html` stores full HTML for 80k pages.
- **vdict_words `friendly` column default is `{}`** (object), not `[]`. Migration `f1b8d293a047` changed this. If you see `[]` in `friendly`, those rows need re-crawling with `--force`.

## Where to look

- `~/.claude/skills/fastapi-async/SKILL.md` — async SQLAlchemy patterns
- `~/.claude/skills/chrome-ext-mv3/SKILL.md` — MV3 service worker quirks, Shadow DOM, Vite multi-entry
- GitHub issues — open items and future work tracked at https://github.com/quniv/vvn-ce/issues
