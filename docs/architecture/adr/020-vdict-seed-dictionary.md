# ADR-020: vdict.com Seed Dictionary as Primary Lookup Source

## Status
Accepted (Phase 8a — crawler in this CR; Phase 8b consumes the data later)

## Context

Calling the LLM for every fresh word lookup costs real money at scale and is slow on first hit (3–10s for words, 10–20s for sentences). The bulk of vocabulary lookups are common dictionary words that don't need a fresh LLM generation — they're identical every time and already exist in any decent bilingual dictionary.

[vdict.com](https://vdict.com) has been Vietnam's largest free Vietnamese-English dictionary since 2004. They publish:
- `robots.txt` and `llms.txt` explicitly allowing crawlers
- Full sitemaps with all word URLs (`sitemap-dict-1-1.xml` + `sitemap-dict-1-2.xml`, totalling ~79,955 URLs for dict_id=1)
- Structured HTML for word entries (academic + friendly definitions, IPA, parts of speech)

Crawling once gives us a free, instant local replacement for ~80% of typical lookups. The LLM stays as a fallback for words not in vdict (rare words, phrasal verbs, slang) and for sentence-level explanations.

## Decision

### Phased approach

Split the integration into three CRs to de-risk:

**Phase 8a (this CR):** Build the crawler. Populate a new `vdict_words` table. **No changes to `/api/explain` or the popup.** Data sits in the DB until inspected.

**Phase 8b (next CR):** After reviewing real crawled data, decide card schema, update LLM fallback prompt shape, wire backend lookup priority `Redis → vdict_words → words → LLM`.

**Phase 8c (later CR):** Refactor sentence flow to use a local n-gram lookup against `vdict_words` — no LLM call for sentence keyword extraction. See [ADR 021](021-local-ngram-sentence-flow.md).

### Crawler design

**Driver:** the sitemap. vdict publishes the exact list of valid URLs. We don't iterate IDs (the URL `meaning,7,0,0.html` uses `7` as `dict_id`, not a word ID).

**URL pattern:** `https://vdict.com/{word},1,0,0.html` for English → Vietnamese.

**Source URLs:**
- `https://vdict.com/sitemaps/sitemap-dict-1-1.xml` — 50,000 entries
- `https://vdict.com/sitemaps/sitemap-dict-1-2.xml` — 29,955 entries

**Schema** (`vdict_words` table):

```sql
CREATE TABLE vdict_words (
    vdict_id     INTEGER PRIMARY KEY,    -- vdict's internal word_id (from data-track-props)
    text         VARCHAR(512) NOT NULL,
    ipa          VARCHAR(256),
    word_type    VARCHAR(64),
    meanings     JSONB NOT NULL DEFAULT '[]',
    friendly     JSONB NOT NULL DEFAULT '[]',
    examples     JSONB NOT NULL DEFAULT '[]',
    raw_html     TEXT,
    crawled_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_vdict_words_lower_text ON vdict_words (LOWER(text));
```

**JSONB flexibility:** we don't know yet exactly how the popup will display this data. JSONB lets us refine the shape without future migrations. `meanings` and `friendly` are arrays of `{pos: string, items: string[]}` initially; can evolve.

**`raw_html` retained:** the parser will inevitably miss edge cases. Storing the raw HTML lets us re-extract fields by re-running just the parser, without re-fetching 80k pages.

**Crawler behaviour:**
- Async (`httpx.AsyncClient`), max 3 concurrent requests, 250ms minimum delay between requests → ~12 req/s peak. Full crawl: ~2 hours.
- Identifies as `User-Agent: vocab-ce-crawler/1.0 (personal use)`.
- Resumable: on start, `SELECT vdict_id FROM vdict_words` and skip already-crawled IDs.
- Idempotent: `INSERT ... ON CONFLICT (vdict_id) DO UPDATE` — re-running is safe and picks up parser improvements.
- Backs off exponentially on 429/5xx, max 60s wait.
- Logs progress every 100 URLs (JSONL to `/tmp/vdict_crawl.jsonl`).
- Aborts loudly on Cloudflare challenge pages.

**HTML parsing** uses `selectolax` (fast lxml-based wrapper). Extract:
- `<h1 class="mb-0">` → `text`
- `<div class="pronunciation">/.../</div>` → `ipa` (first IPA only)
- `data-track-props` JSON → `vdict_id` (the `word_id` field)
- `<div id="academicDefinition">` → list of `<div class="word-type-section">` → `{pos: ..., items: [...]}`
- `<div id="friendlyDefinition">` → similar structure → `friendly`
- `<li class="example">` inside friendlyDefinition → `examples`

`<span class="d_2">` inline tags are stripped (kept as plain text content).

### Scheduling

Not in this CR. The crawler is run manually. Future periodic re-crawl (weekly delta for new words) will be added in Phase 8b — likely as a simple cron job on the host invoking `python -m app.jobs.crawl_vdict`.

## Consequences

**Positive:**
- ~80% of lookups become free + instant once Phase 8b lands.
- vdict is a stable, long-running source (since 2004) — low risk of disappearing.
- Provides actual Vietnamese-Vietnamese-language curated entries (the LLM produces freshly-generated explanations; vdict's are reviewed by humans / sourced from real dictionaries).
- JSONB schema keeps us flexible for the Phase 8b card-shape decision.

**Negative / trade-offs:**
- 80k DB rows + JSONB content: ~150–300 MB total. Acceptable on local disk and on any K8s PostgreSQL.
- Parser maintenance: if vdict changes their HTML, we re-write `parse_entry()` and re-run the crawl (cheap because `raw_html` is cached).
- vdict doesn't have everything: phrasal verbs ("back out of"), idioms ("in the lurch"), and modern slang may be missing. Those fall through to the LLM in Phase 8b.

**Risks:**
- **vdict rate-limits or blocks our IP.** Mitigated by polite headers + slow rate. Worst case: pause, switch to a residential IP, or split the crawl across days.
- **vdict goes offline or significantly changes their HTML.** The crawled data persists in our DB; no immediate impact. Future re-crawls would need parser updates.
- **Legality of the dataset.** Their llms.txt explicitly invites this kind of usage. We don't redistribute the data publicly; it stays on the user's local machine / personal K8s. Standard fair use for educational personal tools.

## Notes

The user's example URL (`https://vdict.com/meaning,7,0,0.html`) confused us at first — the `7` looked like a word ID. Investigation revealed it's the **dictionary ID** (English → English Wordnet). We want **dict_id=1** (English → Vietnamese), the largest dictionary with 100k+ entries (vs. ~80k that we actually crawl from the two sitemaps — the difference is some entries are not in the sitemap, possibly old/deprecated).

Phase 8b will make the decision: drop `synonyms` / `collocations` / `difficulty` from `words` (matching vdict's simpler shape), or keep them and hide-when-empty (mixed-source cards). That decision waits until we see what vdict actually delivers.
