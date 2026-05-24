<script lang="ts">
  import { SvelteSet } from 'svelte/reactivity'
  import { DEFAULT_BACKEND_URL } from '../lib/types'

  type Pair = { id: string; word: string; definition: string }

  let loading = $state(true)
  let error = $state<string | null>(null)
  let words = $state<Pair[]>([])
  let definitions = $state<Pair[]>([])

  let selectedWordId = $state<string | null>(null)
  let selectedDefId = $state<string | null>(null)

  const matched = new SvelteSet<string>()
  const wrongIds = new SvelteSet<string>()
  let attempts = $state(0)
  let correct = $state(0)
  let startTime = 0

  let finished = $derived(words.length > 0 && matched.size === words.length)

  void load()

  async function load() {
    loading = true
    error = null
    try {
      const { backendUrl } = await chrome.storage.local.get('backendUrl')
      const url = (backendUrl as string) || DEFAULT_BACKEND_URL
      const res = await fetch(`${url}/api/game/today`)
      if (!res.ok) throw new Error(`Backend ${res.status}`)
      const body = await res.json()
      const pairs = body.pairs as Pair[]
      words = [...pairs].sort(() => Math.random() - 0.5)
      definitions = [...pairs].sort(() => Math.random() - 0.5)
      startTime = Date.now()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      loading = false
    }
  }

  function pickWord(id: string) {
    if (matched.has(id)) return
    selectedWordId = id
    tryMatch()
  }
  function pickDef(id: string) {
    if (matched.has(id)) return
    selectedDefId = id
    tryMatch()
  }

  function tryMatch() {
    if (!selectedWordId || !selectedDefId) return
    attempts++
    if (selectedWordId === selectedDefId) {
      matched.add(selectedWordId)
      correct++
      selectedWordId = null
      selectedDefId = null
      if (matched.size === words.length) submitResult()
    } else {
      const a = selectedWordId
      const b = selectedDefId
      wrongIds.add(a)
      wrongIds.add(b)
      selectedWordId = null
      selectedDefId = null
      setTimeout(() => {
        wrongIds.delete(a)
        wrongIds.delete(b)
      }, 600)
    }
  }

  async function submitResult() {
    try {
      const { backendUrl } = await chrome.storage.local.get('backendUrl')
      const url = (backendUrl as string) || DEFAULT_BACKEND_URL
      const duration_seconds = Math.round((Date.now() - startTime) / 1000)
      await fetch(`${url}/api/game/result`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          total_words: words.length,
          correct,
          duration_seconds,
        }),
      })
    } catch {
      // ignore
    }
  }
</script>

<section>
  <header>
    <h2>Today's Matching Game</h2>
    <div class="stats">
      <span>Matched: {matched.size} / {words.length}</span>
      <span>Attempts: {attempts}</span>
    </div>
  </header>

  {#if loading}
    <p class="state">Loading today's words…</p>
  {:else if error}
    <p class="state error">Error: {error}</p>
    <button onclick={load}>Retry</button>
  {:else if words.length === 0}
    <p class="state">No words queried today yet. Highlight some text on a webpage to get started!</p>
  {:else if finished}
    <div class="finished">
      <h2>🎉 All matched!</h2>
      <p>Score: {correct} / {words.length} in {attempts} attempts</p>
      <p class="hint">Come back tomorrow with new words.</p>
    </div>
  {:else}
    <div class="board">
      <div class="column">
        <h3>Words</h3>
        {#each words as p (p.id)}
          {@const isMatched = matched.has(p.id)}
          {@const isWrong = wrongIds.has(p.id)}
          {@const isSelected = selectedWordId === p.id}
          <button
            class="card"
            class:matched={isMatched}
            class:wrong={isWrong}
            class:selected={isSelected}
            disabled={isMatched}
            onclick={() => pickWord(p.id)}
          >
            {p.word}
          </button>
        {/each}
      </div>

      <div class="column">
        <h3>Definitions</h3>
        {#each definitions as p (p.id)}
          {@const isMatched = matched.has(p.id)}
          {@const isWrong = wrongIds.has(p.id)}
          {@const isSelected = selectedDefId === p.id}
          <button
            class="card def"
            class:matched={isMatched}
            class:wrong={isWrong}
            class:selected={isSelected}
            disabled={isMatched}
            onclick={() => pickDef(p.id)}
          >
            {p.definition}
          </button>
        {/each}
      </div>
    </div>
  {/if}
</section>

<style>
  section { display: flex; flex-direction: column; gap: 16px; }
  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 12px;
  }
  h2 { margin: 0; font-size: 22px; color: #f1f5f9; }
  .stats {
    display: flex; gap: 18px; color: #94a3b8; font-size: 14px;
  }
  .state { color: #94a3b8; padding: 18px 0; }
  .state.error { color: #fca5a5; }
  .board {
    display: grid;
    grid-template-columns: minmax(220px, 1fr) minmax(220px, 1.5fr);
    gap: 24px;
  }
  .column { display: flex; flex-direction: column; gap: 10px; }
  h3 {
    margin: 0 0 6px;
    color: #94a3b8;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
  }
  .card {
    background: #111c33;
    color: #e2e8f0;
    border: 1px solid #1e293b;
    padding: 14px 16px;
    border-radius: 10px;
    cursor: pointer;
    text-align: left;
    font-size: 15px;
    font-family: inherit;
    transition: background 0.15s, border-color 0.15s;
  }
  .card:hover:not(:disabled) { background: #1e293b; border-color: #334155; }
  .card.def { font-size: 13px; line-height: 1.5; color: #cbd5e1; }
  .card.selected { background: #1e3a8a; border-color: #3b82f6; color: white; }
  .card.matched {
    background: #14532d; border-color: #16a34a; color: #bbf7d0; cursor: default;
  }
  .card.wrong {
    background: #7f1d1d; border-color: #dc2626; animation: shake 0.4s;
  }
  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    25% { transform: translateX(-4px); }
    75% { transform: translateX(4px); }
  }
  .finished {
    background: #111c33;
    padding: 32px;
    border-radius: 14px;
    text-align: center;
    border: 1px solid #1e293b;
  }
  .finished h2 { color: #4ade80; margin: 0 0 12px; }
  .hint { color: #64748b; font-size: 13px; margin: 12px 0 0; }
  button {
    background: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-family: inherit;
    font-size: 13px;
  }
  button:hover { background: #334155; }
</style>
