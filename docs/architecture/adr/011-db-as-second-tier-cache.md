# ADR-011: PostgreSQL as a Second-Tier Cache (Word Dedupe)

## Status
Accepted

## Context

Previously every `POST /api/explain` for a word either hit Redis (fast) or called the LLM (slow). When Redis was flushed or hadn't been warmed, the LLM was called again even though the exact same word — with full explanation — already lived in the `words` table. Two problems:

1. **Wasted LLM calls.** A flushed Redis means every word is re-explained, even ones the user looked up last week.
2. **Duplicate rows.** Every selection inserted a new row, so the `words` table accumulated multiple copies of "ephemeral" or "intricate" — bad for the matching game and any review listing.

## Decision

PostgreSQL becomes a second-tier cache for word lookups. New ordering: **Redis → PostgreSQL → LLM**.

- Add a case-insensitive unique constraint: `CREATE UNIQUE INDEX uq_words_lower_text ON words (LOWER(text))`.
- Add `query_count INTEGER NOT NULL DEFAULT 1` and `last_queried_at TIMESTAMPTZ NOT NULL DEFAULT now()` columns. Repeated queries bump these instead of creating a new row.
- DB lookup only runs for "wordish" inputs: `len(text.strip().split()) <= 2`. Sentences skip the DB step (they're not in the `words` table — only their keywords are).
- The save path uses `INSERT ... ON CONFLICT (LOWER(text)) DO UPDATE SET query_count = query_count + 1, last_queried_at = now() RETURNING *` so a concurrent LLM call from a different request can't insert a duplicate.
- The same UPSERT pattern applies to `/api/words/save` (keyword save flow from sentence selections).
- The response now carries a `db_hit: bool` flag so the popup can show a small "queried Nx from local" indicator when the LLM was skipped.

## Consequences

**Positive:**
- Once a word is in the DB, the LLM is **never** called again for it (until manually deleted).
- The `words` table becomes a true library — one row per word — useful for the matching game, the Word Bank, and any future export.
- `query_count` is a free signal for the user's most-looked-up words.

**Negative / trade-offs:**
- Lose per-selection history (no longer "every time I selected this word"). The trade is acceptable: `query_count` captures frequency.
- Migration must collapse existing duplicates before the unique index is created, or the migration fails on conflict. We hand-write the dedupe step (keep highest net-score row per `LOWER(text)`, sum query_count from the others).

**Risks:**
- **Stale explanation if the LLM changes.** A DB row created by an older model never gets re-explained even if a newer model would do better. Mitigation: a future `/api/words/{id}/regenerate` endpoint can be added when needed.
- **The wordish heuristic gets it wrong** for two-word entries like "back out of" (3 tokens). Those still go through the LLM. Acceptable: phrasal verbs are rare in selection vs. single words, and the cache still handles repeats.

## Notes

`source_url` and `source_sentence` are NOT updated on re-query — they reflect the FIRST place the word was seen. This is fine; the popup doesn't use them.
