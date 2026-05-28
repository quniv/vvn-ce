# ADR-019: Spaced Repetition Practice (Design for the Next CR)

## Status
**Planned — not yet implemented.** The matching game was disabled in Phase 6 (this CR). This ADR captures the full design so Phase 7 can pick it up directly.

## Context

The matching game was a fine prototype for review but doesn't actually drive long-term retention. The user explicitly asked to replace it with a Spaced Repetition workflow ("repeating the word by Spaced Repetition") so words get reviewed at scientifically-motivated intervals.

The canonical SR algorithm for vocabulary is **SM-2** (Anki uses a variant). It's simple, well-understood, and works for personal-scale collections.

## Decision

Implement an SM-2 spaced repetition queue. Each word has a review state (interval, ease, due date, last reviewed). The Practice tab (replacing the disabled Game tab) presents one word at a time with four rating buttons: **Again / Hard / Good / Easy**. Each rating updates the word's SR state per SM-2.

### DB schema additions

Add to the `words` table (single migration):

```sql
ALTER TABLE words
    ADD COLUMN interval_days     INTEGER     NOT NULL DEFAULT 0,
    ADD COLUMN ease_factor       NUMERIC(3,2) NOT NULL DEFAULT 2.5,   -- starting EF per SM-2
    ADD COLUMN due_at            TIMESTAMPTZ NOT NULL DEFAULT now(),  -- new words are immediately due
    ADD COLUMN last_reviewed_at  TIMESTAMPTZ,
    ADD COLUMN review_count      INTEGER     NOT NULL DEFAULT 0;

CREATE INDEX ix_words_due_at ON words (due_at);
```

(`last_queried_at` is unrelated — it tracks "when was this word last looked up in the popup", whereas `last_reviewed_at` tracks "when did the user last grade this word in practice".)

### SM-2 algorithm (Python pseudocode)

```python
def update_sm2(word: Word, rating: Literal['again', 'hard', 'good', 'easy']) -> Word:
    """Anki-flavoured SM-2. Returns updated word fields."""
    q = {'again': 0, 'hard': 3, 'good': 4, 'easy': 5}[rating]

    if q < 3:
        # Failed: reset interval, slight EF penalty
        word.interval_days = 0      # treat as new
        word.review_count = 0
        word.ease_factor = max(1.3, word.ease_factor - 0.20)
        word.due_at = now() + timedelta(minutes=10)   # show again soon in this session
    else:
        word.review_count += 1
        if word.review_count == 1:
            word.interval_days = 1
        elif word.review_count == 2:
            word.interval_days = 6
        else:
            word.interval_days = round(word.interval_days * word.ease_factor)

        # EF update: EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
        ef_delta = 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
        word.ease_factor = max(1.3, word.ease_factor + ef_delta)

        # Easy bonus: bump interval 30% extra
        if rating == 'easy':
            word.interval_days = round(word.interval_days * 1.3)

        word.due_at = now() + timedelta(days=word.interval_days)

    word.last_reviewed_at = now()
    return word
```

### Backend endpoints

```
GET  /api/words/due
  Returns words where due_at <= now(), ordered by due_at ASC, limited (default 50).
  Anonymous OK (or auth-only if voting was unified — TBD when implementing).

POST /api/words/{id}/review
  Body: { rating: "again" | "hard" | "good" | "easy" }
  Applies update_sm2(), returns updated WordRead with the new SR fields.
  Auth: same as vote (must be signed in if we want per-user SR state — but in the current
        single-user-per-installation model, no auth check is fine since the words are shared.)
```

### Frontend — Practice tab

Replace the `GameTab.svelte` placeholder:

```svelte
<!-- src/game/PracticeTab.svelte -->
- On mount: fetch GET /api/words/due
- Render one card at a time (full word card UI: text + IPA + explanation + example etc.)
- Initially the explanation is HIDDEN — only the headword + IPA + word_type are shown
- "Show answer" button reveals the explanation + example + synonyms + collocations
- After reveal, four rating buttons appear: Again / Hard / Good / Easy
- Click → POST /api/words/{id}/review → backend updates → fetch next due word
- When queue is empty: "🎉 All caught up. Come back tomorrow."
```

UI design notes:
- Use the same color palette as the Word Bank (so the user feels at home)
- Rating buttons have colored borders: red (Again), amber (Hard), blue (Good), green (Easy)
- Show a small badge "Reviewed N times · Due in X days after this" in the top right after the user picks a rating, before the next card loads
- Bonus: add a "Hard" button that shows the explanation again without advancing the queue (skip without committing)

### Word bank integration

The Word Bank tab gains a small "Due now / Due tomorrow / Reviewed today" filter to let the user see what's queued. This is nice-to-have, not required for Phase 7.

## Consequences

**Positive:**
- Real-world studying tool. The user reviews each word right when they're about to forget it.
- Builds on the existing word collection — no new content needed.
- Industry-standard algorithm; user can read about SM-2 if curious.
- The Practice tab fits the existing tabbed UI cleanly.

**Negative / trade-offs:**
- Adds 5 columns to the `words` table and a new index. Minor schema bloat.
- The SM-2 algorithm has knobs (ease floor, easy bonus, fail interval) that may need tuning for individual learners. Initial constants come from Anki defaults.
- Multi-user SR is out of scope for v1 — review state is shared across "users" (acceptable since we're single-user in practice).

**Risks:**
- **`due_at` index size** grows with the words table. Negligible.
- **Catastrophic forgetting**: if the user takes a multi-week break, hundreds of words may be due at once. Mitigation: show only the top 20 due each session, document this in the UI ("20 cards due — start practising").

## Notes

The matching game's `/api/game/today` and `/api/game/result` endpoints can be kept around (deprecated) or removed in Phase 7. Frontend stops using them in Phase 6.

If we want **per-user SR state** (different users on different review schedules for the same word), we'd need a `word_review_states(word_id, user_email, interval, ease, due_at, ...)` table — analogous to `word_votes`. Out of scope for Phase 7's first cut; revisit if needed.

References:
- SM-2: https://en.wikipedia.org/wiki/SuperMemo#Description_of_SM-2_algorithm
- Anki manual on the algorithm: https://docs.ankiweb.net/deck-options.html
