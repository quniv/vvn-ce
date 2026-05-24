# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal Chrome Extension + FastAPI backend for English vocabulary learning. Single Vietnamese user. The extension shows a floating "Look up" button when text is selected on any webpage; clicking it opens a popup with a Vietnamese explanation (LLM-generated), synonyms, collocations, difficulty level, and 👍/👎 voting. All looked-up words live in PostgreSQL and are mirrored to `chrome.storage.local` as a browsable Word Bank.

## Stack

| Layer | Technology |
|---|---|
| Extension | Manifest V3, Svelte 5 + Vite, TypeScript |
| Popup overlay | Shadow DOM (style isolation from host pages), dark/light theming |
| Backend | FastAPI (Python 3.14), `uv` for deps |
| Database | PostgreSQL 16 |
| Cache | Redis 7-alpine |
| LLM | OpenRouter → `deepseek/deepseek-v4-flash` (paid, ~cents/month) |
| Orchestration | Docker Compose (local), K8s migration is on the roadmap |

## Common commands

```bash
# Backend
cd backend
uv sync                                       # install deps
uv run uvicorn app.main:app --reload          # local dev (without Docker)

# Alembic (run from backend/, use localhost DATABASE_URL)
DATABASE_URL="postgresql+asyncpg://vocab:vocab@localhost:5432/vocab" \
OPENROUTER_API_KEY="" \
uv run alembic revision --autogenerate -m "<msg>"

DATABASE_URL="postgresql+asyncpg://vocab:vocab@localhost:5432/vocab" \
OPENROUTER_API_KEY="" \
uv run alembic upgrade head

# Extension
cd extension
pnpm install
pnpm build                  # builds dist/  (loads in chrome://extensions as Unpacked)
pnpm check                  # svelte-check, type-check
pnpm build:content          # rebuild content-script IIFE only (faster)

# Full stack (Docker Compose)
docker compose up -d                          # boot db + redis + api
docker compose up -d --force-recreate api     # apply .env / code changes (restart does NOT re-read env_file)
docker compose up -d --force-recreate --renew-anon-volumes --build api   # after `uv add` — the anonymous /app/.venv volume must be renewed
docker compose logs -f api                    # tail backend logs
docker compose ps                             # health
```

## Project layout

```
vocab-ce/
├── backend/                # FastAPI + SQLAlchemy + Redis + OpenRouter proxy
│   ├── app/
│   │   ├── main.py         # FastAPI app + lifespan + routers
│   │   ├── config.py       # pydantic-settings, reads .env
│   │   ├── db.py           # async engine, AsyncSession dep
│   │   ├── models/         # SQLAlchemy ORM
│   │   ├── schemas/        # Pydantic request/response
│   │   ├── routes/         # health, words, game
│   │   └── services/
│   │       ├── cache.py    # Redis wrapper, cache key format
│   │       └── openrouter.py  # SYSTEM_PROMPT + httpx call
│   ├── alembic/            # migrations
│   ├── pyproject.toml      # managed by uv
│   ├── Dockerfile          # python:3.14-slim + uv
│   └── .env                # OPENROUTER_API_KEY, REDIS_URL, OPENROUTER_MODEL, DATABASE_URL
├── extension/              # MV3 Chrome Extension
│   ├── src/
│   │   ├── content/
│   │   │   ├── content-script.ts          # listens for mouseup, mounts Look-up button + Popup (Shadow DOM)
│   │   │   └── popup/
│   │   │       ├── Popup.svelte            # explanation card (themed)
│   │   │       ├── LookupButton.svelte     # floating "🔍 Look up" pill
│   │   │       └── theme.ts                # dark/light helpers + chrome.storage persistence
│   │   ├── background/service-worker.ts    # EXPLAIN/SAVE/VOTE/SYNC_WORDBANK message relay
│   │   ├── options/Options.svelte          # backend URL config
│   │   ├── game/
│   │   │   ├── Game.svelte                  # tab shell (Game | Word Bank)
│   │   │   ├── GameTab.svelte              # matching mini-game
│   │   │   └── WordBank.svelte             # cards grid + filters + sort
│   │   └── lib/types.ts                    # shared TS types + storage key constants
│   ├── manifest.json
│   ├── vite.config.ts             # main build (HTML pages + service-worker)
│   ├── vite.content.config.ts     # separate IIFE build for content script (no ES imports allowed)
│   └── tsconfig.json
├── docker-compose.yml      # db + redis + api
└── docs/architecture/      # READ THIS BEFORE BIG CHANGES
    ├── README.md           # diagrams + data flows
    ├── tech-stack.md       # every layer + alternatives + rationale
    ├── roadmap.md          # phased plan, current state, future K8s
    └── adr/                # numbered Architecture Decision Records (001–015)
```

## Hard conventions

- **Always `uv` for Python.** Never `pip install`, never `python -m venv`. Commands: `uv init`, `uv add`, `uv run`, `uv sync`, `uv lock`, `uv remove`.
- **`docker compose restart` does NOT re-read `env_file`.** After editing `backend/.env`, use `docker compose up -d --force-recreate api`. After `uv add`, also pass `--renew-anon-volumes --build`.
- **Two-file Vite build.** The content script ships as a single IIFE (`vite.content.config.ts`, `inlineDynamicImports: true`) because content scripts can't load ES modules. HTML pages + service worker use the main config (`vite.config.ts`).
- **Shadow DOM is non-negotiable** for any UI mounted into host pages (popup, look-up button). Without it, host CSS will break the popup on any styled site. See `chrome-ext-mv3` skill (`~/.claude/skills/chrome-ext-mv3/SKILL.md`).
- **Backend owns the OpenRouter API key.** The extension never sees it. The model is hardcoded via `OPENROUTER_MODEL` env var — there is no user-facing model picker (see ADR 010).
- **Docs first, then code.** Architecture decisions are tracked in `docs/architecture/adr/` (Status / Context / Decision / Consequences). Update the relevant ADR + README/tech-stack/roadmap BEFORE touching code for any structural change.
- **`words` is deduplicated** on `LOWER(text)` via `uq_words_lower_text` unique index. Use `INSERT ... ON CONFLICT (LOWER(text)) DO UPDATE` (see `_upsert_word` in `backend/app/routes/words.py`).

## Lookup flow (current — see `docs/architecture/README.md` for full version)

```
user selects text on webpage
  → content-script.ts mouseup handler
  → mount LookupButton.svelte in Shadow DOM at selection bbox
  → user clicks the button
  → mount Popup.svelte in Shadow DOM
  → Popup → service-worker → POST /api/explain
     → backend: Redis cache check
        → on miss + wordish input: SELECT FROM words WHERE LOWER(text) = LOWER($1)
           → on DB hit: bump query_count, hydrate Redis, return
        → on full miss: call OpenRouter → cache + UPSERT into words → return
  → Popup renders Vietnamese explanation + synonyms + collocations + difficulty + 👍/👎
  → service-worker fires syncWordBank() in background, refreshing chrome.storage.local
```

## Where to look

- `docs/architecture/README.md` — system diagram, component table, data flows
- `docs/architecture/adr/` — every architectural decision documented (ADRs 001–015)
- `docs/architecture/roadmap.md` — what phases have shipped, what's next
- `~/.claude/skills/fastapi-async/SKILL.md` — async SQLAlchemy patterns and pitfalls
- `~/.claude/skills/chrome-ext-mv3/SKILL.md` — MV3 service worker quirks, Shadow DOM, Vite multi-entry

## Common pitfalls

- **"Cannot read properties of undefined (reading 'sendMessage')"** in the extension popup → the page has a stale content script from a previous build. **Refresh the webpage (F5)** after reloading the extension. `safeSendMessage` in `content-script.ts` now surfaces a clearer message.
- **Alembic migration fails on `LOWER(text)` unique index** → existing duplicates must be collapsed first. See `c98963b230da_richer_word_card_and_dedupe.py` for the pattern (CTE + DELETE before CREATE UNIQUE INDEX).
- **Free OpenRouter models cycle through 429 / 402** upstream. The user has a paid OpenRouter plan; default model is `deepseek/deepseek-v4-flash` (paid, ~$0.10/M input tokens — pennies/month).
- **`chrome.storage.local.wordBank`** can drift from backend after vote / save actions if `syncWordBank()` fails silently. The Word Bank tab has a manual "↻ refresh" button.
