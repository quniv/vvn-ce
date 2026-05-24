# ADR-009: Word Voting with Integer Counters (no per-user history)

## Status
Accepted

## Context

The user wanted a way to mark which saved words are worth revisiting. After reading an explanation, a quick 👍 / 👎 should let them indicate "this is important to me" or "I knew this already, low priority". Words with higher net scores should surface first in the matching game and any future review listings.

Three voting schemas were considered:

1. **Integer counters on the `words` row** — `up_vote` (int), `down_vote` (int), incremented atomically on each vote.
2. **Per-vote audit rows** — separate `word_votes(word_id, direction, voted_at)` table.
3. **Per-user vote tracking** — store one row per (user, word) and a single mutable direction per user.

Option 3 is overengineered for a single-user tool. Option 2 is overengineered for personal use; the audit trail is information the user doesn't need. Option 1 is enough.

## Decision

Add two integer columns to `words`:

```sql
ALTER TABLE words
  ADD COLUMN up_vote   INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN down_vote INTEGER NOT NULL DEFAULT 0;
```

And one new endpoint:

```
POST /api/words/{id}/vote
body: { "direction": "up" | "down" }
```

The endpoint increments the corresponding counter and returns the updated `WordRead`. Each click adds 1; there is no dedup per user (single-user tool). Multiple clicks on 👍 simply add more weight — that's a feature, not a bug ("strongly want to study this more").

All listing endpoints (`GET /api/words`, `GET /api/words/today`, `GET /api/game/today`) order by:

```sql
ORDER BY (up_vote - down_vote) DESC, created_at DESC
```

## Consequences

**Positive:**
- Trivial schema change — two new INT columns.
- Vote endpoint is one async DB update.
- No new tables, no foreign keys, no audit history to maintain.
- The matching game and any future review screen automatically surface high-priority words.

**Negative / trade-offs:**
- **No history.** We don't know when votes happened or how many votes each word has accumulated over time — just the totals.
- **No undo.** Clicking 👍 by mistake means clicking 👎 to neutralize; you can't subtract a vote you made.
- **No abuse protection.** Not relevant for a single-user tool, but means the same design doesn't generalize to multi-user.

**Risks:**
- **Race condition on concurrent votes** — extremely unlikely with a single user clicking serially, but use `UPDATE words SET up_vote = up_vote + 1 WHERE id = $1` (atomic) rather than read-modify-write.

## Notes

`model_source` is added in the same migration as the vote columns since both touch the `words` table. `model_source` records the OpenRouter model id that produced the explanation, so the user can see at a glance "this explanation came from GLM-4.5 Air" and revote / regenerate accordingly.

Future enhancement (out of scope): a `/api/words/{id}/regenerate` endpoint that calls OpenRouter again, updates `explanation` + `example` + `model_source`, and resets `up_vote`/`down_vote` to 0.
