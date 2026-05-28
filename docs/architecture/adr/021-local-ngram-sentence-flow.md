# ADR-021: Local n-gram Sentence Flow (No LLM Call for Keyword Extraction)

## Status
**Planned — not implemented.** Phase 8a (current CR) only seeds the `vdict_words` table. This ADR captures the design for Phase 8c so the follow-up CR can pick it up directly.

## Context

The current sentence flow calls the LLM to (1) extract noteworthy keywords from the selection and (2) write a Vietnamese explanation of the sentence as a whole. The LLM call takes 10–20 seconds. This is the slowest interaction in the extension.

Once `vdict_words` is populated with ~80k English-Vietnamese entries (Phase 8a), we can extract keywords locally by scanning the sentence for substrings that exist in the dictionary. This is what "n-gram lookup" means here.

## Decision

For sentence input (`len(text.split()) > 2`):

1. **Tokenize** the sentence into words (whitespace + simple punctuation strip).
2. **Generate n-grams** of length 1–4 over the token list. Example: "back out of the deal" → `back, out, of, the, deal, back out, out of, of the, the deal, back out of, out of the, of the deal, back out of the, out of the deal`.
3. **Look up each n-gram** in `vdict_words` (case-insensitive, batched: a single `SELECT ... WHERE LOWER(text) = ANY($1)` with all candidates).
4. **Longest-match wins**: when both "back out" and "back out of" exist in vdict, prefer "back out of" and exclude "back out" from the result if it overlaps.
5. **Skip stop-words** (the, is, and, a, an, to, of, ...) when they appear as single tokens. They're rarely the interesting vocabulary.
6. **Return the matched n-grams as keyword chips** in the popup. Total elapsed time: ~100ms.

For the sentence-level explanation (the paragraph that summarises the whole sentence's meaning), we have two options to decide in Phase 8c:

- **Drop it.** The user picks chips and learns words. The sentence is just context.
- **Stream from LLM in the background.** Show chips at 100ms; the sentence paragraph fills in over ~3–5s as LLM tokens stream. Best UX, more code.

This ADR doesn't pre-commit; Phase 8c will decide based on UX feel.

## Schema

No new DB tables. Uses the existing `vdict_words` from [ADR 020](020-vdict-seed-dictionary.md):

```sql
-- Batched lookup (called once per sentence selection)
SELECT text, vdict_id, ipa, word_type, meanings, friendly
FROM vdict_words
WHERE LOWER(text) = ANY($1)   -- $1 = array of all 1- to 4-gram candidates, lowercased
ORDER BY length(text) DESC;   -- longest match first
```

The `ix_vdict_words_lower_text` index handles this efficiently. For a 20-word sentence, ~80 candidates → one indexed lookup → <10ms.

## Frontend behaviour

The popup's sentence flow needs no schema changes. The current `ExplainResponse.keywords` array is preserved; the only difference is who populates it (backend's local lookup, not the LLM).

Chips render exactly as today — `text`, `word_type` badge, on-click to save into `words` via existing `/api/words/save`.

## Endpoint

New endpoint: `POST /api/sentence-keywords` body `{text: string}` → returns `KeywordItem[]`. Replaces the sentence path in `/api/explain`.

Or keep `/api/explain` and just branch internally on `_is_wordish(text)`:
- word → existing flow
- sentence → new local lookup, returns `kind: "sentence"` with `keywords[]` and a NULL `explanation` (or LLM-streamed explanation if we decide to keep it)

The latter is cleaner — preserve the contract.

## Consequences

**Positive:**
- Sentence latency drops from 10–20s to <200ms.
- Zero LLM cost for sentence selections.
- Works offline (after the initial vdict crawl).

**Negative / trade-offs:**
- Sentence-level summary paragraph is lost (or becomes a streaming delight, depending on Phase 8c decision).
- Misses words not in vdict (rare/slang/very-new). Acceptable: keyword lists tend to surface the COMMON difficult words, which vdict has.
- N-gram explosion for very long sentences: a 30-word sentence has ~120 candidates. Still one batched DB query, still fast.

**Risks:**
- **Overlap bookkeeping in longest-match.** Mitigated by sorting matches by length DESC and tracking covered token spans. Standard algorithm, ~30 LOC.
- **Stop-word list is locale-specific.** English stop-words are well-known; we use NLTK's standard list (no NLTK dep — just hard-code ~50 words).

## Notes

When Phase 8c lands, the popup's "keyword chips → click to save" UX stays identical. The only user-visible difference: chips appear instantly instead of after a 10s spinner.

Hybrid future direction: rare/unknown n-grams could fall through to a fast LLM call (DeepSeek V4 Flash, ~3s) just for those words — best of both worlds. Out of scope here.
