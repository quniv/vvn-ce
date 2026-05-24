# ADR-012: Richer Word Card Structure (Synonyms, Collocations, Difficulty)

## Status
Accepted

## Context

The original card had: word, type, IPA, Vietnamese explanation, English example. Good for a quick lookup, but a vocabulary learner gains more from related-word context and difficulty awareness:

- **Synonyms** anchor a new word in the mental map of words already known.
- **Collocations** teach the natural multi-word patterns the word participates in — often the gap between "understanding" and "using" a word.
- **Difficulty** lets the user filter the Word Bank by what's worth practising most (intermediate/advanced) vs. already-easy (beginner).

Other candidates considered (antonyms, common mistakes for Vietnamese learners, related forms like noun/verb/adj versions) were dropped for now to keep the card focused. They can be added later by extending the prompt and schema.

## Decision

Extend the LLM JSON contract with three new fields. The exact contract is documented in `docs/architecture/tech-stack.md` §9.

| Field | Type | Required | Notes |
|---|---|---|---|
| `synonyms` | `list[str]` | yes (can be empty) | 3–5 single-word English synonyms |
| `collocations` | `list[str]` | yes (can be empty) | 2–5 common multi-word phrases using the word |
| `difficulty` | `"beginner" \| "intermediate" \| "advanced"` | yes | Single enum string |

For **sentence-mode responses**, each entry in `keywords[]` also includes these three fields — keywords get saved as full word rows when the user picks them.

Schema additions to `words`: `synonyms JSONB NOT NULL DEFAULT '[]'`, `collocations JSONB NOT NULL DEFAULT '[]'`, `difficulty VARCHAR(16) NULL`.

## Consequences

**Positive:**
- Card is more useful for vocabulary learning at glance.
- Word Bank filters can use `difficulty` and `synonyms` to slice the library.
- LLM cost per call increases negligibly (~50 extra output tokens, ~$0.00001/call).

**Negative / trade-offs:**
- Card height grows; in the popup this is fine because we cap height with overflow-y. The popup already scrolls when needed.
- Older rows (created before this contract) have `synonyms = []`, `collocations = []`, `difficulty = NULL`. The popup must hide empty sections gracefully — done via Svelte `{#if list.length > 0}` and `{#if difficulty}` guards.

**Risks:**
- **The LLM occasionally returns fewer than 3 synonyms** for rare words. Acceptable — better to show what the model knows than to retry.
- **The LLM may produce wrong difficulty labels.** Mitigation: vote down + manually re-query later (regen endpoint, future).

## Notes

Card layout (top to bottom in the popup):
1. Headword + type badge + difficulty badge + IPA (header row)
2. Vietnamese explanation (~100 words)
3. Example sentence (italic, English)
4. Synonyms (small chips)
5. Collocations (bulleted list)
6. Vote buttons + cache/db_hit indicator + "queried Nx" counter
