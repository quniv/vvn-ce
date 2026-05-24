# ADR-010: Hardcode the LLM Model in the Backend (Roll Back the CE Picker)

## Status
Accepted (supersedes [ADR-006](006-models-sync-job.md) and [ADR-007](007-client-model-selection.md))

## Context

ADR-007 introduced a per-request model field so the extension's Options page could let the user pick which LLM produced explanations. ADR-006 supported it with a daily sync job that mirrored OpenRouter's model catalog into PostgreSQL.

In practice, choosing the model from the UI added complexity for very little upside:

- This is a single-user personal tool. The user almost always wants the same model.
- Free models cycle through upstream rate limits unpredictably — the user-facing dropdown surfaced this churn without solving it.
- The catalog sync, APScheduler, `/api/models` route, and the dropdown UI together accounted for ~400 LOC and one extra background task — disproportionate to the value.

The simpler design: backend reads `OPENROUTER_MODEL` from `.env` (currently `z-ai/glm-4.5-air:free`). Changing it is one `.env` edit plus a container restart — easy enough that we don't need a UI.

## Decision

Remove the user-facing model picker entirely. Hardcode the model in the backend via the existing `OPENROUTER_MODEL` env var (default `z-ai/glm-4.5-air:free`):

**Backend removals:**
- Drop `/api/models` route and `app/routes/models.py`
- Drop `app/jobs/` (`sync_models.py`, `scheduler.py`, package)
- Drop `app/models/model_catalog.py` (and its `__init__.py` re-export)
- Drop `app/schemas/model.py`
- Drop `apscheduler` from `pyproject.toml`
- Alembic migration: `DROP TABLE openrouter_models`
- `ExplainRequest` no longer accepts a `model` field
- `openrouter.explain(text)` signature reverts — always uses `settings.openrouter_model`
- `app/main.py` lifespan removes scheduler start/stop and bootstrap-sync call

**Frontend removals:**
- `Options.svelte`: remove the model dropdown, the "Show all" toggle, and the "Refresh models" button — only the backend URL field remains
- `service-worker.ts`: remove the `selectedModel` lookup and stop including `model` in EXPLAIN/SAVE payloads
- `types.ts`: remove `ModelInfo`; remove `model` from the `EXPLAIN` and `SAVE_KEYWORDS` payload types
- `chrome.storage.local` no longer holds `selectedModel`

**Retained from the prior work:**
- `model_source` column on `words` — the backend still records which model produced each row, populated from `settings.openrouter_model`. Useful for debugging and harmless.
- The Vietnamese ~100-word prompt (ADR-008) stays.
- The Redis explanation cache (ADR-005) stays. Cache key still includes the model id, which is now constant.

## Consequences

**Positive:**
- ~400 LOC removed; one fewer background task; one fewer DB table; one fewer route.
- Options page is back to a single field (backend URL).
- Backend boot is faster (no scheduler, no bootstrap sync).
- One less moving part to debug when something goes wrong.

**Negative:**
- Switching models requires editing `.env` and restarting the API container. Acceptable for a personal tool.
- If the hardcoded model goes upstream-rate-limited (free-tier reality), the user must edit `.env` to switch — there's no quick UI escape hatch.

**Risks:**
- **Forgot-to-recreate-on-env-change:** `docker compose restart` does not re-read `env_file`. The user must use `docker compose up -d --force-recreate api`. Documented in roadmap and tech-stack.

## Notes

If model selection ever comes back, the schema work (`OpenRouterModel`) and the standalone sync callable (`app/jobs/sync_models.py`) are documented in superseded ADRs 006/007 and can be reconstructed from git history without much pain. The cache and `model_source` column already exist to support per-model semantics if it returns.
