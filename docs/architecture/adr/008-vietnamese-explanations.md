# ADR-008: Vietnamese-Language Explanations, ~100 Words

## Status
Accepted

## Context

The original system prompt asked the LLM to "explain in an easy way" but did not pin a language or length. In practice, the model returned English explanations of varying length (sometimes 1 sentence, sometimes a paragraph) which is not optimal for the user's learning workflow.

Goals:
- The user is Vietnamese and finds Vietnamese explanations easier to absorb than English ones.
- Explanations should be a consistent length — not so short they miss nuance, not so long they overwhelm the popup.
- Pronunciation (IPA) and example sentences should remain in English; they are the **study targets**, not study aids.

## Decision

Update the SYSTEM_PROMPT to require:

1. **`explanation` field is in Vietnamese.** Target ~100 words (50–150 acceptable range).
2. **`word_type`** stays as a short tag like `n`, `v`, `adj`, `phrasal verb`, `idiom`.
3. **`pronunciation`** stays in IPA (e.g. `/ˌser.ənˈdɪp.ə.ti/`).
4. **`example`** stays in English — it is the sentence the user will study using the new word.

For sentence inputs:
- The top-level `explanation` is in Vietnamese (the sentence summary).
- Each `keywords[].explanation` is in Vietnamese.
- Each `keywords[].example` is in English (a different example sentence using that keyword).

The prompt explicitly says: *"Reply in Vietnamese in the `explanation` field. Aim for ~100 words. Do not include English in `explanation` except for proper nouns or words being directly quoted."*

## Consequences

**Positive:**
- The user can absorb the meaning faster (native-language explanations).
- Consistent length improves popup layout (no more 1-line vs. 1-paragraph variance).
- Study workflow is clearer: read Vietnamese explanation → understand → study the English example to lock in usage.

**Negative / trade-offs:**
- Models vary in Vietnamese quality. Some free models (small Llamas, small Gemmas) produce awkward Vietnamese. The user can switch to a better model via the Options page (see [ADR 007](007-client-model-selection.md)).
- Word count target is a soft hint — the model may return 60-word or 180-word explanations. We accept the response either way; we do **not** retry to enforce a length range. (Retries would burn free-tier quota.)

**Risks:**
- **Model occasionally returns English** even when prompted for Vietnamese. The popup renders whatever is returned — the user can see this and switch models if it keeps happening.
- **JSON schema unchanged from English-output days** — only the field semantics changed, not the field names or types. No code migration needed.

## Notes

If word-count enforcement becomes important later, the cheapest mitigation is to add a post-processing check in the backend: if `len(explanation.split()) < 30 or > 200`, append a flag in the response so the popup can show a "regenerate" button. Out of scope for v1.

The prompt is in `backend/app/services/openrouter.py` and is the single source of truth for output format.
