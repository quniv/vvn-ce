# ADR-005: Use Redis 7 as the LLM Response Cache

## Status
Accepted

## Context

Every text selection triggers an LLM call to OpenRouter, which takes 2–20 seconds and consumes free-tier daily quota. For a personal tool used many times a day, the same vocabulary is selected repeatedly — the second selection of "serendipity" should be instant.

Three caching options were considered:

1. **Redis** — a dedicated in-memory key-value store, native TTL support, industry standard.
2. **PostgreSQL cache table** — reuse the existing database with a `cache_entries(key, value, expires_at)` table.
3. **In-memory Python LRU** — a dict inside the FastAPI process.

## Decision

Use **Redis 7-alpine** as a third Docker service (`vocab-redis`). Adopt the cache-aside pattern:

- **Key format:** `explain:{model_id}:{sha256(text.strip().lower())}`
- **Value:** the full `ExplainResponse` JSON serialized as a string
- **TTL:** 30 days (`EX 2592000`)

`(model_id, text)` is the cache key — switching the active model produces a different cache namespace automatically, so no flush is needed when the user picks a new model in the Options page.

## Consequences

**Positive:**
- Repeat lookups return in <100ms instead of 2–20s.
- Free-tier OpenRouter quota is preserved for genuinely new vocabulary.
- TTL is native (no manual expiry sweep needed).
- Maps cleanly to a managed Redis or operator-deployed Redis when migrating to Kubernetes.

**Negative / trade-offs:**
- One more Docker service (≈30MB RAM, one more thing that can fail).
- Cache lives in RAM — if the `redis` container restarts without the persistent volume, the cache is cold. Acceptable for a personal tool; a cold cache is just slower, not broken.
- Redis is now a runtime dependency. The API will fail-soft if Redis is unreachable (treat as cache miss, log the error), but if the user wants the API to start without Redis, they need to disable cache via env var (not in scope yet).

**Risks:**
- **Stale explanations if a better model is published.** Mitigated because the model id is part of the cache key — using a new model creates a new namespace; the old namespace expires naturally in 30 days.
- **The same word from different sentences hits the same cache entry.** Acceptable because the explanation is for the word in isolation; sentence-level explanations have the full sentence as the cache key text.

## Notes

The cache stores LLM **responses**, not `Word` rows. Saved words are still persisted in PostgreSQL on every selection (with the votes that accumulate over time). Cache and persistent storage are independent concerns.

For K8s migration: swap `vocab-redis` for a managed Redis instance or the Bitnami Redis Helm chart. `REDIS_URL` env var changes; no code changes.
