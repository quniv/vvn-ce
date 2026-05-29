# ADR-006: Daily Model Catalog Sync via APScheduler (with K8s CronJob path)

## Status
**Superseded by [ADR-010](010-hardcode-model-no-picker.md)** — the model-picker UI was rolled back, so there is no consumer for a synced model catalog. The catalog table, the sync job, and APScheduler were all removed.

## Context

The extension's Options page needs a dropdown of available OpenRouter models. Two architectural shapes were considered:

1. **Live proxy** — `GET /api/models` calls OpenRouter on every Options page load.
2. **Daily sync into PostgreSQL** — a background job pulls the model catalog into a local `openrouter_models` table; `GET /api/models` reads from the local table.

The daily sync is much faster for the user (single SELECT vs. external HTTPS call), continues to work if OpenRouter is briefly unreachable, and keeps the Options page responsive.

The next question: **where does the daily job run?**

- **APScheduler in-process** — schedule the job inside the FastAPI container.
- **Separate scheduler container** — a small dedicated service.
- **Host crontab** — external `cron` calling an admin endpoint.
- **K8s CronJob** — best practice for K8s, but the user is still on Docker Compose.

## Decision

Use **APScheduler `AsyncIOScheduler` in-process**, started/stopped via the FastAPI `lifespan` context manager. Register a single job: `app.jobs.sync_models:sync_models` daily at 06:00 local time.

**Crucially, `sync_models()` is implemented as a standalone async callable** that can also be invoked via `python -m app.jobs.sync_models`. This makes the K8s migration trivial: drop APScheduler, replace it with a K8s `CronJob` that runs the same Python module. No business logic changes.

On API startup, the `lifespan` also checks whether `openrouter_models` is empty; if so it kicks off a one-shot sync so the first run has data without waiting until 06:00 the next day.

## Consequences

**Positive:**
- Zero extra infrastructure on Docker Compose.
- Single-replica today; the in-process scheduler is correct.
- Same async runtime as the rest of the API; no separate process management.
- K8s migration is a deployment change, not a code change.

**Negative / trade-offs:**
- If the API container restarts at 05:59, the 06:00 run is missed. APScheduler has misfire policies but a missed daily sync is harmless — the data is at most ~24h old anyway.
- If the API ever scales to multiple replicas in K8s **without** migrating the job out, every replica will run the sync. This is documented and the migration target is a `CronJob`.

**Risks:**
- **OpenRouter returns 6xx during sync** — handled with retry-once-then-fail logic; existing rows stay (UPSERT, no DELETE first).
- **APScheduler vs FastAPI lifespan ordering** — start scheduler before yielding from `lifespan`, stop it on shutdown. Standard pattern.

## Notes

Schema for the local catalog (see `docs/architecture/tech-stack.md` §4):

```sql
CREATE TABLE openrouter_models (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    context_length INTEGER,
    pricing_prompt NUMERIC,
    pricing_completion NUMERIC,
    is_free BOOLEAN NOT NULL,
    raw JSONB NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Upsert on `id` (`ON CONFLICT DO UPDATE`). Set `synced_at = now()`. Rows for models that disappear from OpenRouter are left in place; the route can hide stale rows by filtering on `synced_at >= now() - interval '7 days'` if needed.

K8s migration path (no code change):

```yaml
apiVersion: batch/v1
kind: CronJob
spec:
  schedule: "0 6 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: sync-models
              image: vvn-api:latest
              command: ["python", "-m", "app.jobs.sync_models"]
              envFrom: [{ secretRef: { name: vocab-secrets } }]
          restartPolicy: OnFailure
```
