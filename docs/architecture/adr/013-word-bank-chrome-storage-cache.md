# ADR-013: Word Bank in `chrome.storage.local`, Mirrored from Backend

## Status
Accepted

## Context

The user wants to browse every word they've ever queried — a "word bank". The backend already stores everything in `words`, so the question is only about the read path:

1. **Each open fetches `GET /api/words`** — simplest, no duplication, but requires the backend to be reachable every time and adds latency to opening the tab.
2. **Mirror into `chrome.storage.local`** — instant load, works offline, but adds a sync concern.
3. **Primary write into `chrome.storage.local`, secondary into the backend** — true offline-first, but introduces conflict resolution and a 5 MB hard cap on browser storage.

Option 1 means a blank UI for a second on every open. Option 3 is over-engineered for a single-user tool. Option 2 hits the sweet spot — backend remains the source of truth, the UI is always fast.

## Decision

The Word Bank tab reads from `chrome.storage.local.wordBank` on mount (instant), then triggers a background sync via the service worker. The sync writes the freshest `/api/words` snapshot back to storage. Conflict resolution is "backend wins on every refresh" — no merging, no LWW per-field — the entire array is replaced.

**Sync triggers:**
- Service worker fires `syncWordBank()` (fire-and-forget) after every successful EXPLAIN / SAVE_KEYWORDS / VOTE response — so the cache stays warm without the user opening the tab.
- The Word Bank tab also sends a `SYNC_WORDBANK` message on mount, awaiting the response to replace the rendered list.
- A "Refresh" button on the tab manually re-triggers `SYNC_WORDBANK`.

**Storage schema:**

```ts
chrome.storage.local: {
  backendUrl: string
  wordBank: WordRead[]          // mirror of /api/words?limit=1000
  wordBankSyncedAt: string      // ISO-8601
}
```

## Consequences

**Positive:**
- Word Bank tab opens **instantly** — no spinner, no network wait.
- Works **offline** for browsing words you've already seen.
- Sync is "free" because it happens as a side effect of normal usage.

**Negative / trade-offs:**
- Two sources of word data on the client: the popup's response (one word) and the bank cache. They can momentarily disagree if a sync hasn't fired yet — but the popup's response is also passed straight to the sync trigger, so disagreement lasts at most ~100ms.
- The `wordBank` cache only carries the rows; vote actions still need a network round-trip to update the backend.

**Risks:**
- **5 MB quota.** A `WordRead` row averages ~400 bytes; ~12,500 words fit. For a personal tool used over years this is comfortable. If we ever approach the limit, we can drop the bottom 20% by net-score on each sync.
- **Sync failure (backend unreachable).** The stored copy is returned as-is; the UI shows the cached `wordBankSyncedAt` so the user knows it might be stale. No retries — next EXPLAIN or manual Refresh will sync again.

## Notes

The Word Bank UI presents words from the cached array. Vote buttons in the bank are out of scope for this iteration (the user can vote from the popup when looking the word up again). If voting in the bank becomes needed later: the bank tab sends VOTE → backend → triggers `syncWordBank()` → bank tab re-renders.
