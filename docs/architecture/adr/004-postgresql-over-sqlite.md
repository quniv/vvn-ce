# ADR 004 — PostgreSQL 16 over SQLite for local + Kubernetes portability

**Status:** Accepted

---

## Context

This is a single-user personal tool running on a developer's local machine. SQLite would be technically sufficient for the data volume. The question is whether the convenience of SQLite is worth the migration cost when the system moves to Kubernetes.

Options considered:

**Option A:** SQLite — zero Docker dependency, file-based, no server process, trivial setup.

**Option B:** PostgreSQL 16 in Docker — full relational DB with Docker Compose.

**Option C:** MongoDB — flexible schema, good Docker support.

---

## Decision

**PostgreSQL 16 in Docker**, managed by Docker Compose alongside the FastAPI backend.

---

## Consequences

**Positive:**
- K8s migration is a copy/restore operation: `pg_dump` from the Docker volume → restore to a K8s StatefulSet or CloudNativePG-managed instance. No schema translation, no data transformation, no ORM changes
- Native UUID support (`gen_random_uuid()`) for the `id` column
- `TIMESTAMPTZ` (timezone-aware timestamps) for `created_at` and `reviewed_at` — correct behavior across timezone changes without extra conversion logic
- CloudNativePG operator support — production-grade PostgreSQL on K8s without managing a StatefulSet manually
- Future multi-user capability without architectural changes
- `asyncpg` provides excellent async PostgreSQL support for FastAPI

**Negative:**
- Docker must be running for the extension to work (alongside the FastAPI backend — Docker is already required)
- Slightly more initial setup than SQLite

**Risk:** Docker named volume (`pgdata`) is not automatically backed up — a `docker volume rm` or accidental `docker compose down -v` would destroy all saved vocabulary.

**Mitigation:** Add a `pg_dump` to a daily cron script from day one:

```bash
# Daily backup (add to crontab or systemd timer)
docker exec vvn-db pg_dump -U vocab vocab > ~/backups/vocab-$(date +%Y%m%d).sql
```

This should be configured before any meaningful vocabulary data accumulates.
