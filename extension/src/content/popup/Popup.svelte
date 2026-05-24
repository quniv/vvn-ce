<script lang="ts">
  import { SvelteSet } from 'svelte/reactivity'
  import type {
    ExplainResponse,
    ExplainResult,
    KeywordItem,
    Message,
    SaveResult,
    VoteDirection,
    VoteResult,
  } from '../../lib/types'
  import { effectiveTheme, getStoredTheme, setStoredTheme } from './theme'

  type Props = {
    selectedText: string
    sourceUrl: string
    onClose: () => void
    sendMessage: (msg: Message) => Promise<unknown>
  }

  const { selectedText, sourceUrl, onClose, sendMessage }: Props = $props()

  let loading = $state(true)
  let error = $state<string | null>(null)
  let result = $state<ExplainResponse | null>(null)
  const selected = new SvelteSet<number>()
  let saveStatus = $state<'idle' | 'saving' | 'saved' | 'error'>('idle')
  let saveError = $state<string | null>(null)
  let voteBusy = $state(false)
  let theme = $state<'dark' | 'light'>('dark')

  // Init theme + kick off the fetch once when the component is created
  void initTheme()
  void fetchExplain()

  async function initTheme() {
    theme = effectiveTheme(await getStoredTheme())
  }

  async function toggleTheme() {
    const next: 'dark' | 'light' = theme === 'dark' ? 'light' : 'dark'
    theme = next
    await setStoredTheme(next)
  }

  async function vote(direction: VoteDirection) {
    if (!result || !result.saved_id || voteBusy) return
    voteBusy = true
    try {
      const res = (await sendMessage({
        type: 'VOTE',
        payload: { wordId: result.saved_id, direction },
      })) as VoteResult
      if (res.ok) {
        result = { ...result, up_vote: res.data.up_vote, down_vote: res.data.down_vote }
      }
    } finally {
      voteBusy = false
    }
  }

  async function fetchExplain() {
    loading = true
    error = null
    try {
      const res = (await sendMessage({
        type: 'EXPLAIN',
        payload: { text: selectedText, source_url: sourceUrl },
      })) as ExplainResult
      if (!res.ok) {
        error = res.error
      } else {
        result = res.data
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      loading = false
    }
  }

  function toggleChip(i: number) {
    if (selected.has(i)) selected.delete(i)
    else selected.add(i)
  }

  async function saveSelected() {
    if (!result || selected.size === 0) return
    saveStatus = 'saving'
    saveError = null
    const keywords: KeywordItem[] = [...selected].map((i) => result!.keywords[i])
    try {
      const res = (await sendMessage({
        type: 'SAVE_KEYWORDS',
        payload: {
          source_sentence: result.text,
          source_url: sourceUrl,
          keywords,
        },
      })) as SaveResult
      if (res.ok) {
        saveStatus = 'saved'
        setTimeout(onClose, 1200)
      } else {
        saveStatus = 'error'
        saveError = res.error
      }
    } catch (e) {
      saveStatus = 'error'
      saveError = e instanceof Error ? e.message : String(e)
    }
  }
</script>

<div class="card theme-{theme}" role="dialog">
  <button class="theme-btn" aria-label="Toggle theme" onclick={toggleTheme}>
    {theme === 'dark' ? '☀️' : '🌙'}
  </button>
  <button class="close" aria-label="Close" onclick={onClose}>×</button>

  {#if loading}
    <div class="state">
      <div class="spinner"></div>
      <span>Explaining…</span>
    </div>
  {:else if error}
    <div class="state error">
      <strong>Error</strong>
      <pre>{error}</pre>
      <button class="btn" onclick={fetchExplain}>Retry</button>
    </div>
  {:else if result}
    {#if result.kind === 'word'}
      <header class="word-header">
        <h1>{result.text}</h1>
        {#if result.word_type}
          <span class="badge">{result.word_type}</span>
        {/if}
        {#if result.difficulty}
          <span class="badge difficulty difficulty-{result.difficulty}">{result.difficulty}</span>
        {/if}
        {#if result.pronunciation}
          <span class="pron">{result.pronunciation}</span>
        {/if}
      </header>
      <p class="explanation">{result.explanation}</p>
      {#if result.example}
        <p class="example">"<em>{result.example}</em>"</p>
      {/if}
      {#if result.synonyms && result.synonyms.length > 0}
        <div class="extra-block">
          <div class="extra-label">Synonyms</div>
          <div class="syn-chips">
            {#each result.synonyms as s (s)}
              <span class="syn-chip">{s}</span>
            {/each}
          </div>
        </div>
      {/if}
      {#if result.collocations && result.collocations.length > 0}
        <div class="extra-block">
          <div class="extra-label">Collocations</div>
          <ul class="colloc-list">
            {#each result.collocations as c (c)}
              <li>{c}</li>
            {/each}
          </ul>
        </div>
      {/if}
      {#if result.saved && result.saved_id}
        <div class="vote-row">
          <button
            class="vote-btn up"
            class:active={result.up_vote > 0}
            onclick={() => vote('up')}
            disabled={voteBusy}
            title="Worth studying more"
          >
            👍 {result.up_vote}
          </button>
          <button
            class="vote-btn down"
            class:active={result.down_vote > 0}
            onclick={() => vote('down')}
            disabled={voteBusy}
            title="I know this already"
          >
            👎 {result.down_vote}
          </button>
          {#if result.query_count && result.query_count > 1}
            <span class="query-count" title="Times you've looked this up">
              ×{result.query_count}
            </span>
          {/if}
          <span class="source-tag">
            {#if result.cached}⚡ cached{:else if result.db_hit}📚 from bank{:else}✨ fresh{/if}
          </span>
        </div>
      {/if}
    {:else}
      <header class="sentence-header">
        <h2>{result.text}</h2>
      </header>
      <p class="explanation">{result.explanation}</p>

      {#if result.model_source}
        <div class="model-source-sentence">
          {result.cached ? '⚡ cached' : '✨ fresh'} · {result.model_source}
        </div>
      {/if}
      {#if result.keywords.length > 0}
        <div class="chips-label">Keywords — pick what to save:</div>
        <div class="chips">
          {#each result.keywords as kw, i (kw.text + i)}
            {@const isSelected = selected.has(i)}
            <button
              type="button"
              class="chip"
              class:selected={isSelected}
              onclick={() => toggleChip(i)}
              title={kw.explanation}
            >
              <span class="chip-text">{kw.text}</span>
              {#if kw.word_type}
                <span class="chip-type">{kw.word_type}</span>
              {/if}
            </button>
          {/each}
        </div>

        {#if selected.size > 0}
          <div class="selected-preview">
            {#each [...selected] as i (i)}
              {@const kw = result.keywords[i]}
              <div class="kw-detail">
                <div class="kw-detail-head">
                  <strong>{kw.text}</strong>
                  {#if kw.word_type}<span class="badge small">{kw.word_type}</span>{/if}
                  {#if kw.difficulty}<span class="badge small difficulty difficulty-{kw.difficulty}">{kw.difficulty}</span>{/if}
                  {#if kw.pronunciation}<span class="pron small">{kw.pronunciation}</span>{/if}
                </div>
                <div class="kw-detail-body">{kw.explanation}</div>
                {#if kw.example}<div class="kw-detail-example">"<em>{kw.example}</em>"</div>{/if}
                {#if kw.synonyms && kw.synonyms.length > 0}
                  <div class="kw-syn">
                    {#each kw.synonyms as s (s)}<span class="syn-chip small">{s}</span>{/each}
                  </div>
                {/if}
              </div>
            {/each}
          </div>

          <button
            class="btn primary save-btn"
            onclick={saveSelected}
            disabled={saveStatus === 'saving'}
          >
            {#if saveStatus === 'saving'}
              Saving…
            {:else if saveStatus === 'saved'}
              Saved ✓
            {:else}
              Save {selected.size} selected
            {/if}
          </button>
          {#if saveStatus === 'error' && saveError}
            <div class="state error compact">{saveError}</div>
          {/if}
        {/if}
      {:else}
        <div class="footer-tag">No notable keywords</div>
      {/if}
    {/if}
  {/if}
</div>

<style>
  :host,
  * {
    box-sizing: border-box;
  }

  /* ── Theme palette (dark = default) ─────────────────────────── */
  .card {
    --bg: rgba(15, 23, 41, 0.9);
    --heading: #f1f5f9;
    --text: #e2e8f0;
    --body: #cbd5e1;
    --muted: #94a3b8;
    --dim: #64748b;
    --line: #334155;
    --surface: #1e293b;
    --surface-2: #111c33;
    --accent: #3b82f6;
    --accent-hover: #2563eb;
    --accent-soft-bg: #1e3a8a;
    --accent-soft-text: #dbeafe;
    --badge-bg: #1e3a8a;
    --badge-text: #93c5fd;
    --quote-line: #334155;
    --error-text: #fca5a5;
    --error-bg: #1e293b;
    --error-pre-text: #fecaca;
    --vote-up-bg: #14532d;
    --vote-up-border: #16a34a;
    --vote-up-text: #bbf7d0;
    --vote-down-bg: #7f1d1d;
    --vote-down-border: #dc2626;
    --vote-down-text: #fecaca;
    --diff-beg-bg: #14532d;
    --diff-beg-text: #bbf7d0;
    --diff-int-bg: #713f12;
    --diff-int-text: #fde68a;
    --diff-adv-bg: #7f1d1d;
    --diff-adv-text: #fecaca;
    --shadow: 0 10px 32px rgba(0, 0, 0, 0.5);
    --primary-disabled-bg: #475569;
  }

  /* ── Light palette: OS-detected ─────────────────────────────── */
  @media (prefers-color-scheme: light) {
    .card:not(.theme-dark) {
      --bg: rgba(255, 255, 255, 0.93);
      --heading: #0f172a;
      --text: #1e293b;
      --body: #334155;
      --muted: #64748b;
      --dim: #94a3b8;
      --line: #cbd5e1;
      --surface: #f1f5f9;
      --surface-2: #f8fafc;
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --accent-soft-bg: #dbeafe;
      --accent-soft-text: #1e40af;
      --badge-bg: #dbeafe;
      --badge-text: #1e40af;
      --quote-line: #cbd5e1;
      --error-text: #b91c1c;
      --error-bg: #fee2e2;
      --error-pre-text: #7f1d1d;
      --vote-up-bg: #dcfce7;
      --vote-up-border: #86efac;
      --vote-up-text: #14532d;
      --vote-down-bg: #fee2e2;
      --vote-down-border: #fca5a5;
      --vote-down-text: #991b1b;
      --diff-beg-bg: #dcfce7;
      --diff-beg-text: #14532d;
      --diff-int-bg: #fef3c7;
      --diff-int-text: #78350f;
      --diff-adv-bg: #fee2e2;
      --diff-adv-text: #991b1b;
      --shadow: 0 6px 24px rgba(15, 23, 41, 0.18);
      --primary-disabled-bg: #cbd5e1;
    }
  }

  /* ── Light palette: explicit class (overrides media query) ── */
  .card.theme-light {
    --bg: rgba(255, 255, 255, 0.93);
    --heading: #0f172a;
    --text: #1e293b;
    --body: #334155;
    --muted: #64748b;
    --dim: #94a3b8;
    --line: #cbd5e1;
    --surface: #f1f5f9;
    --surface-2: #f8fafc;
    --accent: #2563eb;
    --accent-hover: #1d4ed8;
    --accent-soft-bg: #dbeafe;
    --accent-soft-text: #1e40af;
    --badge-bg: #dbeafe;
    --badge-text: #1e40af;
    --quote-line: #cbd5e1;
    --error-text: #b91c1c;
    --error-bg: #fee2e2;
    --error-pre-text: #7f1d1d;
    --vote-up-bg: #dcfce7;
    --vote-up-border: #86efac;
    --vote-up-text: #14532d;
    --vote-down-bg: #fee2e2;
    --vote-down-border: #fca5a5;
    --vote-down-text: #991b1b;
    --diff-beg-bg: #dcfce7;
    --diff-beg-text: #14532d;
    --diff-int-bg: #fef3c7;
    --diff-int-text: #78350f;
    --diff-adv-bg: #fee2e2;
    --diff-adv-text: #991b1b;
    --shadow: 0 6px 24px rgba(15, 23, 41, 0.18);
    --primary-disabled-bg: #cbd5e1;
  }

  /* ── Layout & component styles (use vars) ──────────────────── */
  .card {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    border-radius: 12px;
    box-shadow: var(--shadow);
    width: 380px;
    max-width: 92vw;
    padding: 16px 18px;
    font-size: 14px;
    line-height: 1.5;
    position: relative;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
  }

  .close, .theme-btn {
    position: absolute;
    top: 8px;
    background: transparent;
    border: none;
    color: var(--dim);
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
    line-height: 1;
  }
  .close {
    right: 10px;
    font-size: 22px;
  }
  .theme-btn {
    right: 42px;
    font-size: 14px;
    top: 11px;
  }
  .close:hover, .theme-btn:hover {
    color: var(--text);
    background: var(--surface);
  }

  h1, h2 {
    margin: 0;
    color: var(--heading);
    font-weight: 600;
  }
  h1 { font-size: 22px; }
  h2 { font-size: 15px; line-height: 1.4; font-style: italic; color: var(--body); }

  .word-header {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px;
    padding-right: 68px;
    margin-bottom: 10px;
  }
  .sentence-header {
    padding-right: 68px;
    margin-bottom: 10px;
  }

  .badge {
    background: var(--badge-bg);
    color: var(--badge-text);
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .badge.small { font-size: 10px; padding: 1px 6px; }

  .pron {
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 13px;
  }
  .pron.small { font-size: 11px; }

  .explanation {
    margin: 8px 0;
    color: var(--body);
  }
  .example {
    margin: 8px 0 0;
    color: var(--muted);
    font-size: 13px;
    border-left: 2px solid var(--quote-line);
    padding-left: 10px;
  }

  .footer-tag {
    margin-top: 12px;
    color: var(--dim);
    font-size: 12px;
    text-align: right;
  }

  .state {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--muted);
    padding: 8px 0;
  }
  .state.error {
    flex-direction: column;
    align-items: flex-start;
    color: var(--error-text);
  }
  .state.error pre {
    background: var(--error-bg);
    padding: 8px;
    border-radius: 6px;
    width: 100%;
    margin: 4px 0;
    font-size: 12px;
    overflow-x: auto;
    color: var(--error-pre-text);
    white-space: pre-wrap;
    word-break: break-word;
  }
  .state.compact { padding: 6px 0; font-size: 12px; }

  .spinner {
    width: 14px;
    height: 14px;
    border: 2px solid var(--line);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .chips-label {
    margin: 12px 0 8px;
    font-size: 12px;
    color: var(--muted);
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    background: transparent;
    color: var(--body);
    border: 1px solid var(--line);
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 13px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: inherit;
  }
  .chip:hover {
    background: var(--surface);
  }
  .chip.selected {
    background: var(--accent-soft-bg);
    border-color: var(--accent);
    color: var(--accent-soft-text);
  }
  .chip-type {
    font-size: 10px;
    text-transform: uppercase;
    opacity: 0.75;
    letter-spacing: 0.5px;
  }

  .selected-preview {
    margin-top: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 240px;
    overflow-y: auto;
  }
  .kw-detail {
    background: var(--surface-2);
    padding: 8px 10px;
    border-radius: 8px;
  }
  .kw-detail-head {
    display: flex;
    align-items: baseline;
    gap: 6px;
    flex-wrap: wrap;
    margin-bottom: 4px;
  }
  .kw-detail-body {
    color: var(--body);
    font-size: 13px;
  }
  .kw-detail-example {
    color: var(--muted);
    font-size: 12px;
    margin-top: 4px;
  }

  .btn {
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--line);
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    font-family: inherit;
  }
  .btn:hover { background: var(--line); }
  .btn.primary {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  .btn.primary:hover { background: var(--accent-hover); }
  .btn.primary:disabled {
    background: var(--primary-disabled-bg);
    border-color: var(--primary-disabled-bg);
    cursor: default;
  }
  .save-btn {
    margin-top: 10px;
    width: 100%;
  }

  .vote-row {
    margin-top: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .vote-btn {
    background: transparent;
    color: var(--body);
    border: 1px solid var(--line);
    padding: 4px 12px;
    border-radius: 999px;
    cursor: pointer;
    font-family: inherit;
    font-size: 13px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .vote-btn:hover:not(:disabled) { background: var(--surface); }
  .vote-btn.up.active {
    background: var(--vote-up-bg);
    border-color: var(--vote-up-border);
    color: var(--vote-up-text);
  }
  .vote-btn.down.active {
    background: var(--vote-down-bg);
    border-color: var(--vote-down-border);
    color: var(--vote-down-text);
  }
  .vote-btn:disabled { opacity: 0.6; cursor: default; }

  .model-source {
    margin-left: auto;
    font-size: 11px;
    color: var(--dim);
    font-family: ui-monospace, monospace;
  }
  .model-source-sentence {
    margin-top: 6px;
    font-size: 11px;
    color: var(--dim);
    font-family: ui-monospace, monospace;
    text-align: right;
  }

  .badge.difficulty { text-transform: capitalize; letter-spacing: 0; }
  .badge.difficulty-beginner    { background: var(--diff-beg-bg); color: var(--diff-beg-text); }
  .badge.difficulty-intermediate { background: var(--diff-int-bg); color: var(--diff-int-text); }
  .badge.difficulty-advanced    { background: var(--diff-adv-bg); color: var(--diff-adv-text); }

  .extra-block { margin-top: 10px; }
  .extra-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--dim);
    margin-bottom: 4px;
  }
  .syn-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }
  .syn-chip {
    background: var(--surface);
    color: var(--body);
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 12px;
    border: 1px solid var(--line);
  }
  .syn-chip.small {
    font-size: 11px;
    padding: 1px 6px;
  }
  .colloc-list {
    margin: 0;
    padding-left: 18px;
    color: var(--body);
    font-size: 13px;
    line-height: 1.55;
  }
  .colloc-list li { margin: 1px 0; }
  .kw-syn {
    margin-top: 6px;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .query-count {
    font-size: 11px;
    color: var(--muted);
    font-family: ui-monospace, monospace;
  }
  .source-tag {
    margin-left: auto;
    font-size: 11px;
    color: var(--dim);
    font-family: ui-monospace, monospace;
  }
</style>
