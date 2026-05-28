# ADR-022: Google Translate (Unofficial) for Sentence Flow — Drop LLM and Keyword Chips

## Status
Accepted

## Context

Sentence flow latency is the slowest interaction in the extension — the LLM takes 10–20 seconds for a fresh sentence selection. The LLM's output served two purposes:

1. A Vietnamese explanation of the whole sentence
2. A list of "keyword chips" — phrasal verbs / idioms / uncommon words — that the user could click to save into the Word Bank

Both came from the same expensive call. The user has been pushing for speed and cost reductions:

- Phase 8a seeded a local `vdict_words` table from vdict.com — a free dictionary source
- Now: replace the sentence's expensive LLM call with Google Translate's unofficial endpoint

Google's free unofficial endpoint `https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=...` returns Vietnamese in well under one second. It only provides the whole-sentence translation — no per-word keyword extraction.

The user explicitly chose to **drop the keyword chips entirely** rather than keep them via the LLM. Per-word saving is still possible by highlighting individual words (which uses the word flow → vdict_words / LLM fallback).

## Decision

**For sentence input** (`len(text.split()) > 2`):

- Call `https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=<urlencoded>`
- Cache the result in Redis at `gt:en-vi:{sha256(text.strip().lower())}` with the same 30-day TTL as LLM cache
- Return `ExplainResponse(kind="sentence", text=<original>, explanation=<vi translation>, keywords=[], model_source="google-translate", cached=<bool>)`
- **No DB write, no LLM call, no keyword extraction.**

**For word input** (`len(text.split()) <= 2`): unchanged — keeps the existing Redis → Postgres → LLM ladder.

**Popup behaviour**: when `kind == 'sentence'` and `keywords.length === 0` (which is always now), simply show the original English sentence + the Vietnamese translation. No "Keywords — pick what to save" section, no "No notable keywords" placeholder.

## Consequences

**Positive:**
- Sentence latency drops from ~10–20s to <1s.
- Zero LLM cost for sentence selections.
- No HTTP authentication needed — the unofficial endpoint is open.
- Cache key namespaced as `gt:en-vi:…` keeps GT data separate from LLM data; switching translation providers later is one config flip.

**Negative / trade-offs:**
- Keyword chips are gone. To save individual words from a sentence, the user must re-highlight just that word. This was an explicit user decision.
- The unofficial Google endpoint isn't documented or contractually stable. Google could change the response shape or rate-limit us. Mitigations:
  - Polite headers (User-Agent, Accept-Language)
  - Light request volume (one call per sentence selection — well below typical rate limits)
  - Cache hits return immediately, so a single user generates only a few uncached translations per day

**Risks:**
- **Endpoint deprecation.** If Google removes `/translate_a/single` we fall back to the LLM with a clean swap in `google_translate.py` (single failure point).
- **IP rate-limit.** At typical personal-use rates (~10 sentence lookups/day) this is far below any plausible limit.
- **Quality.** Google Translate's Vietnamese is generally good, but occasionally awkward. The user can highlight any unclear word individually for the rich LLM/dictionary explanation.

## Notes

The response shape from the endpoint is a nested array:

```json
[
  [["<translated vi>","<original en>",null,null,3,null,null,[[]],[[["<hash>","<model.md>"]]]]],
  null,
  "en",     // detected source language
  null,
  ...
]
```

Parser extracts `response[0][0][0]` for the translation string. Multi-sentence inputs concatenate as `response[0][i][0]` for each `i` — we join with spaces.

Detected source language is at `response[2]` and could be useful in the future (auto-detect Vietnamese → English direction), but for v1 we hardcode `sl=en`.

If Google Translate becomes unavailable, the user sees a 502 from `/api/explain`. The popup already handles this gracefully (Retry button). Out of scope for this ADR: fallback to LLM on GT failure.
