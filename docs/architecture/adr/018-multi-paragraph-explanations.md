# ADR-018: Multi-Paragraph Vietnamese Explanations

## Status
Accepted (refines [ADR-008](008-vietnamese-explanations.md))

## Context

ADR-008 specified the `explanation` field as Vietnamese text targeting ~100 words. In practice the model returns a single dense paragraph, which is visually heavy in the popup and hard to scan. A typical popup card has the headword + IPA + word_type + difficulty + explanation + example + synonyms + collocations — the explanation block dominates as a wall of text.

Breaking the explanation into 2–4 short paragraphs (definition / nuance / usage examples / common pitfalls) makes the card much easier to read at a glance.

## Decision

Update the SYSTEM_PROMPT to require **2 to 4 short paragraphs** for the `explanation` field, separated by **blank lines** (i.e., the LLM puts `\n\n` between paragraphs). Total word count stays at ~100 words (acceptable range 50–150). Each paragraph 20–50 words.

Suggested paragraph structure (not enforced):
1. **Definition** — core meaning in plain Vietnamese
2. **Nuance / register** — when to use it, formal vs. informal, connotations
3. **Common contexts** — what it's typically said about, common collocations summarized
4. **Pitfalls** — false friends, confusable words, common Vietnamese-learner mistakes (skip if none)

The popup renders the field with `white-space: pre-line` in CSS, which preserves the `\n\n` as visual paragraph breaks.

**No schema change.** `explanation` is still a TEXT column holding a single string.

## Consequences

**Positive:**
- Card is much easier to scan; the user can jump to the section they need.
- Zero migration cost — older single-paragraph rows still render fine (just one paragraph).
- The LLM is already producing structured prose; asking for paragraphs is a low-risk prompt change.

**Negative / trade-offs:**
- Token usage may grow slightly (paragraph break characters + minor verbosity). Negligible cost impact.
- Some models occasionally ignore the paragraph instruction and return a single block. Acceptable — they're still readable.

**Risks:**
- **Existing cached responses** (in Redis or DB) are single-paragraph. New queries get paragraphs; old cached words don't. The user can force a re-fetch by clearing Redis for that word. Out of scope to auto-migrate.

## Notes

The popup's `.explanation` and `.kw-detail-body` CSS classes need `white-space: pre-line` so `\n` in the text becomes a visual line break. `pre-line` collapses runs of spaces but preserves single newlines and blank lines — exactly what we want for paragraph rendering.
