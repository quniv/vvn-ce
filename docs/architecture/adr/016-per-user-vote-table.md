# ADR-016: Per-User Vote Table Replacing Integer Counters

## Status
Accepted (supersedes [ADR-009](009-word-voting.md))

## Context

ADR-009 chose integer `up_vote` / `down_vote` counters directly on the `words` row for simplicity (single-user tool). With the introduction of Google sign-in for voting, we need per-user vote attribution — who voted what, so the popup can highlight the user's own vote and so future moderation / multi-user scenarios work.

Three schemas were considered:

1. **Integer counters + a separate audit table.** Keep `up_vote`/`down_vote` on words for fast reads, add a `word_votes` table for audit. Doubles writes; counters and audit can drift.
2. **Per-user vote table only, aggregates computed on read.** One row per `(word_id, user_email)`, listings JOIN/aggregate.
3. **Per-user vote table + denormalized counter columns.** Best of both, but adds write complexity (must keep counters in sync with the table).

For our use case (< 10k words per user, no analytics on votes), aggregate cost is negligible.

## Decision

Replace the integer counters with a dedicated `word_votes` table:

```sql
CREATE TABLE word_votes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    word_id     UUID NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    user_email  VARCHAR(320) NOT NULL,
    direction   VARCHAR(4) NOT NULL CHECK (direction IN ('up', 'down')),
    voted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_word_votes_word_user ON word_votes (word_id, user_email);
CREATE INDEX ix_word_votes_word_id ON word_votes (word_id);
```

**Toggle semantics** (Reddit-style):
- No existing row for `(word_id, user_email)` → INSERT new row
- Existing row with **same direction** → DELETE (the user un-votes)
- Existing row with **opposite direction** → UPDATE direction

**Aggregates on read**: listings compute `up_vote` and `down_vote` via subqueries (or a single LEFT JOIN with `COUNT FILTER`) and include the current authenticated user's `user_vote: 'up' | 'down' | null`. Ordering remains `(up - down) DESC, last_queried_at DESC`.

The existing `words.up_vote` and `words.down_vote` columns are **dropped** in the same migration. Historical anonymous votes are lost — acceptable since they were essentially worthless without per-user attribution anyway.

## Consequences

**Positive:**
- Per-user accuracy: the popup can highlight which button the **current user** pressed, not just "someone".
- Foundation for future multi-user / sharing scenarios.
- `ON DELETE CASCADE` keeps things clean when a word is deleted.
- Single vote per `(word_id, user_email)` enforced by the unique index.

**Negative / trade-offs:**
- Every listing now does aggregate computation. For ~10k words and ~1k votes per user, this is < 5ms in PostgreSQL — acceptable.
- Bulk vote-import is no longer trivial — every row needs a user.

**Risks:**
- **Aggregate query plan changes** as data grows. Mitigation: `ix_word_votes_word_id` makes per-word aggregates fast.
- **Migration drops data.** Existing votes (integer counters) are not migrated to the new schema (we don't know who voted). This is documented in the migration script and roadmap.

## Notes

`user_email` is a free-text VARCHAR(320) — we don't have a `users` table yet. The email comes from Google's authenticated userinfo, so it's trustworthy. Adding a `users` table is a future concern; for now, the email is sufficient.
