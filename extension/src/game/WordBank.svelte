<script lang="ts">
  import {
    WORDBANK_STORAGE_KEY,
    WORDBANK_SYNCED_AT_KEY,
    WORDBANK_OPTIONS_KEY,
    type Message,
    type WordBankResponse,
    type WordRead,
    type WordBankOptions,
  } from '../lib/types'

  type SortKey = 'recent' | 'most_queried' | 'alphabetical'
  type DifficultyFilter = 'all' | 'beginner' | 'intermediate' | 'advanced'
  type TypeFilter = 'all' | string
  type DateFilter = 'today' | 'week' | 'month' | 'all'

  let words = $state<WordRead[]>([])
  let syncedAt = $state<string | null>(null)
  let syncing = $state(false)
  let syncError = $state<string | null>(null)
  let storageUsageKB = $state(0)

  let search = $state('')
  let difficulty = $state<DifficultyFilter>('all')
  let typeFilter = $state<TypeFilter>('all')
  let sortKey = $state<SortKey>('recent')
  let dateFilter = $state<DateFilter>('today')
  let retentionDays = $state(30)

  // Build a list of unique word_types for the filter dropdown
  let availableTypes = $derived(() => {
    const s = new Set<string>()
    for (const w of words) {
      if (w.word_type) s.add(w.word_type)
    }
    return Array.from(s).sort()
  })

  let filtered = $derived.by(() => {
    const q = search.trim().toLowerCase()
    const now = new Date()
    const retentionThreshold = new Date(now.getTime() - retentionDays * 24 * 60 * 60 * 1000)
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000)
    const monthAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000)

    let list = words.filter((w) => {
      if (q && !w.text.toLowerCase().includes(q)) return false
      if (difficulty !== 'all' && w.difficulty !== difficulty) return false
      if (typeFilter !== 'all' && w.word_type !== typeFilter) return false

      // Apply date filter and retention
      if (dateFilter !== 'all') {
        const lastQueriedTime = new Date(w.last_queried_at)
        if (dateFilter === 'today') {
          const itemToday = new Date(lastQueriedTime)
          itemToday.setHours(0, 0, 0, 0)
          if (itemToday.getTime() !== today.getTime()) return false
        } else if (dateFilter === 'week') {
          if (lastQueriedTime < weekAgo) return false
        } else if (dateFilter === 'month') {
          if (lastQueriedTime < monthAgo) return false
        }
      }

      // Apply retention (hide old items unless showing all)
      if (dateFilter !== 'all' && new Date(w.last_queried_at) < retentionThreshold) return false

      return true
    })
    switch (sortKey) {
      case 'recent':
        list.sort((a, b) => b.last_queried_at.localeCompare(a.last_queried_at))
        break
      case 'most_queried':
        list.sort((a, b) => b.query_count - a.query_count)
        break
      case 'alphabetical':
        list.sort((a, b) => a.text.localeCompare(b.text))
        break
    }
    return list
  })

  void init()

  async function init() {
    // 1. Instant load from chrome.storage
    const stored = await chrome.storage.local.get([
      WORDBANK_STORAGE_KEY,
      WORDBANK_SYNCED_AT_KEY,
      WORDBANK_OPTIONS_KEY,
    ])
    if (Array.isArray(stored[WORDBANK_STORAGE_KEY])) {
      words = stored[WORDBANK_STORAGE_KEY] as WordRead[]
    }
    if (typeof stored[WORDBANK_SYNCED_AT_KEY] === 'string') {
      syncedAt = stored[WORDBANK_SYNCED_AT_KEY] as string
    }
    if (stored[WORDBANK_OPTIONS_KEY]) {
      const opts = stored[WORDBANK_OPTIONS_KEY] as WordBankOptions
      dateFilter = opts.dateFilter ?? 'today'
      retentionDays = opts.retentionDays ?? 30
    }
    await updateStorageUsage()
    // 2. Refresh from backend
    await refresh()
  }

  async function updateStorageUsage() {
    try {
      const bytes = await chrome.storage.local.getBytesInUse(null)
      storageUsageKB = Math.ceil(bytes / 1024)
    } catch (e) {
      console.error('Failed to get storage usage:', e)
    }
  }

  async function saveOptions() {
    try {
      await chrome.storage.local.set({
        [WORDBANK_OPTIONS_KEY]: { dateFilter, retentionDays },
      })
    } catch (e) {
      console.error('Failed to save options:', e)
    }
  }

  async function refresh() {
    syncing = true
    syncError = null
    try {
      const msg: Message = { type: 'SYNC_WORDBANK' }
      const res = (await chrome.runtime.sendMessage(msg)) as WordBankResponse
      if (res.ok) {
        words = res.data
        syncedAt = res.syncedAt
        await updateStorageUsage()
      } else {
        syncError = res.error
      }
    } finally {
      syncing = false
    }
  }

  function formatRelative(iso: string | null): string {
    if (!iso) return 'never'
    const ms = Date.now() - new Date(iso).getTime()
    if (ms < 60_000) return 'just now'
    const m = Math.floor(ms / 60_000)
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    const d = Math.floor(h / 24)
    return `${d}d ago`
  }

</script>

<section>
  <header>
    <h2>Word Bank</h2>
    <div class="meta">
      <span>{filtered.length} of {words.length}</span>
      <span class="sync-info">synced {formatRelative(syncedAt)}</span>
      <span class="storage-info">Storage: {storageUsageKB} KB</span>
    </div>
  </header>

  <div class="retention-info">
    Showing words from last <strong>{retentionDays}</strong> days
  </div>

  <div class="controls">
    <input
      type="search"
      placeholder="Search words…"
      bind:value={search}
    />
    <div class="date-filter">
      <button
        class:active={dateFilter === 'today'}
        onclick={() => {
          dateFilter = 'today'
          void saveOptions()
        }}
      >
        Today
      </button>
      <button
        class:active={dateFilter === 'week'}
        onclick={() => {
          dateFilter = 'week'
          void saveOptions()
        }}
      >
        Week
      </button>
      <button
        class:active={dateFilter === 'month'}
        onclick={() => {
          dateFilter = 'month'
          void saveOptions()
        }}
      >
        Month
      </button>
      <button
        class:active={dateFilter === 'all'}
        onclick={() => {
          dateFilter = 'all'
          void saveOptions()
        }}
      >
        All
      </button>
    </div>
    <select bind:value={difficulty}>
      <option value="all">All levels</option>
      <option value="beginner">Beginner</option>
      <option value="intermediate">Intermediate</option>
      <option value="advanced">Advanced</option>
    </select>
    <select bind:value={typeFilter}>
      <option value="all">All types</option>
      {#each availableTypes() as t (t)}
        <option value={t}>{t}</option>
      {/each}
    </select>
    <select bind:value={sortKey}>
      <option value="recent">Most recent</option>
      <option value="most_queried">Most queried</option>
      <option value="alphabetical">A → Z</option>
    </select>
  </div>

  {#if syncError}
    <p class="state error">Sync error: {syncError} (showing cached data)</p>
  {/if}

  {#if words.length === 0}
    <p class="state">
      Your word bank is empty. Highlight any English word or sentence on a webpage to start
      building it.
    </p>
  {:else if filtered.length === 0}
    <p class="state">No words match the current filters.</p>
  {:else}
    <div class="grid">
      {#each filtered as w (w.id)}
        <div class="word-card">
          <div class="head">
            <strong>{w.text}</strong>
            {#if w.word_type}<span class="badge">{w.word_type}</span>{/if}
            {#if w.difficulty}<span class="badge difficulty difficulty-{w.difficulty}">{w.difficulty}</span>{/if}
          </div>
          {#if w.pronunciation}<div class="ipa">{w.pronunciation}</div>{/if}
          <p class="explanation">{w.explanation}</p>
          {#if w.example}
            <p class="example">"<em>{w.example}</em>"</p>
          {/if}
          {#if w.synonyms && w.synonyms.length > 0}
            <div class="extra">
              <div class="extra-label">Synonyms</div>
              <div class="syn-chips">
                {#each w.synonyms as s (s)}<span class="syn-chip">{s}</span>{/each}
              </div>
            </div>
          {/if}
          {#if w.collocations && w.collocations.length > 0}
            <div class="extra">
              <div class="extra-label">Collocations</div>
              <ul class="colloc-list">
                {#each w.collocations as c (c)}<li>{c}</li>{/each}
              </ul>
            </div>
          {/if}
          <div class="foot">
            <span class="qc">×{w.query_count}</span>
            <span class="when">{formatRelative(w.last_queried_at)}</span>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  section { display: flex; flex-direction: column; gap: 14px; }
  header {
    display: flex; justify-content: space-between; align-items: baseline;
    flex-wrap: wrap; gap: 12px;
  }
  h2 { margin: 0; font-size: 22px; color: #f1f5f9; }
  .meta {
    display: flex; gap: 14px; align-items: center; color: #94a3b8; font-size: 13px;
  }
  .sync-info { font-size: 12px; color: #64748b; font-family: ui-monospace, monospace; }
  .storage-info { font-size: 12px; color: #64748b; font-family: ui-monospace, monospace; }
  .retention-info {
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 12px;
  }

  .controls {
    display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
  }
  input[type="search"], select {
    background: #0f1729;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 13px;
    font-family: inherit;
  }
  input[type="search"] { flex: 1 1 200px; min-width: 200px; }
  select { cursor: pointer; }
  input:focus, select:focus { outline: none; border-color: #3b82f6; }

  .date-filter {
    display: flex;
    gap: 4px;
    background: #0f1729;
    border: 1px solid #334155;
    padding: 2px;
    border-radius: 8px;
  }
  .date-filter button {
    background: transparent;
    color: #94a3b8;
    border: none;
    padding: 6px 12px;
    cursor: pointer;
    font-size: 13px;
    border-radius: 6px;
    transition: background 0.15s, color 0.15s;
    font-family: inherit;
  }
  .date-filter button:hover { color: #e2e8f0; }
  .date-filter button.active {
    background: #1e293b;
    color: #3b82f6;
  }

  .state { color: #94a3b8; padding: 18px 0; }
  .state.error { color: #fca5a5; }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }
  .word-card {
    background: #111c33;
    color: #e2e8f0;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 14px 16px;
    font-family: inherit;
    text-align: left;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .head {
    display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  }
  .head strong { font-size: 17px; color: #f1f5f9; }
  .badge {
    background: #1e3a8a;
    color: #93c5fd;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.2px;
  }
  .badge.difficulty { text-transform: capitalize; }
  .badge.difficulty-beginner { background: #14532d; color: #bbf7d0; }
  .badge.difficulty-intermediate { background: #713f12; color: #fde68a; }
  .badge.difficulty-advanced { background: #7f1d1d; color: #fecaca; }
  .ipa { color: #94a3b8; font-family: ui-monospace, monospace; font-size: 12px; }
  .explanation {
    margin: 0;
    color: #cbd5e1;
    font-size: 13px;
    line-height: 1.55;
  }
  .example {
    margin: 0;
    color: #94a3b8;
    font-size: 13px;
    border-left: 2px solid #334155;
    padding-left: 10px;
  }
  .extra { display: flex; flex-direction: column; gap: 4px; }
  .extra-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #64748b;
  }
  .syn-chips { display: flex; flex-wrap: wrap; gap: 5px; }
  .syn-chip {
    background: #1e293b;
    color: #cbd5e1;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 12px;
    border: 1px solid #334155;
  }
  .colloc-list {
    margin: 0; padding-left: 18px; color: #cbd5e1; font-size: 12px; line-height: 1.6;
  }
  .foot {
    display: flex; gap: 10px; align-items: center; font-size: 12px;
    color: #94a3b8; font-family: ui-monospace, monospace;
  }
  .foot .qc { margin-left: auto; }
  .foot .when { color: #64748b; }
</style>
