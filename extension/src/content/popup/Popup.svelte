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
    onMove?: (newX: number, newY: number) => void
    getPosition?: () => { x: number; y: number }
    onDragStart?: () => void
    onDragEnd?: () => void
  }

  const { selectedText, sourceUrl, onClose, sendMessage, onMove, getPosition, onDragStart, onDragEnd }: Props = $props()

  let dragStart: { mouseX: number; mouseY: number; hostX: number; hostY: number } | null = null

  function handleDragStart(e: MouseEvent) {
    if (!onMove || !getPosition) return
    e.preventDefault()
    const pos = getPosition()
    dragStart = { mouseX: e.clientX, mouseY: e.clientY, hostX: pos.x, hostY: pos.y }
    onDragStart?.()
    window.addEventListener('mousemove', handleDragMove)
    window.addEventListener('mouseup', handleDragEnd)
  }

  function handleDragMove(e: MouseEvent) {
    if (!dragStart || !onMove) return
    onMove(
      dragStart.hostX + (e.clientX - dragStart.mouseX),
      dragStart.hostY + (e.clientY - dragStart.mouseY),
    )
  }

  function handleDragEnd() {
    dragStart = null
    onDragEnd?.()
    window.removeEventListener('mousemove', handleDragMove)
    window.removeEventListener('mouseup', handleDragEnd)
  }

  let loading = $state(true)
  let error = $state<string | null>(null)
  let result = $state<ExplainResponse | null>(null)
  const selected = new SvelteSet<number>()
  let saveStatus = $state<'idle' | 'saving' | 'saved' | 'error'>('idle')
  let saveError = $state<string | null>(null)
  let voteBusy = $state(false)
  let voteError = $state<string | null>(null)
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
    voteError = null
    try {
      const res = (await sendMessage({
        type: 'VOTE',
        payload: { wordId: result.saved_id, direction },
      })) as VoteResult
      if (res.ok) {
        result = {
          ...result,
          up_vote: res.data.up_vote,
          down_vote: res.data.down_vote,
          user_vote: res.data.user_vote ?? null,
        }
      } else {
        voteError = res.error
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
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div class="drag-handle" role="separator" aria-label="Move card" onmousedown={handleDragStart}>⠿</div>
  <button class="theme-btn" aria-label="Toggle theme" onclick={toggleTheme}>
    {theme === 'dark' ? '☀️' : '🌙'}
  </button>
  <button class="close" aria-label="Close" onclick={onClose}>×</button>

  <div class="card-body">
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
        {#if result.audio_url}
          <button
            class="audio-btn"
            aria-label="Play pronunciation"
            onclick={() => new Audio(result!.audio_url!).play()}
          >▶</button>
        {/if}
      </header>
      <p class="explanation">{result.explanation}</p>

      {#if result.vdict_examples && result.vdict_examples.length > 0}
        <div class="extra-block">
          <div class="extra-label">Examples</div>
          <div class="example-pairs">
            {#each result.vdict_examples as ex (ex.en)}
              <div class="example-pair">
                <span class="ex-en">{ex.en}</span>
                <span class="ex-vi">{ex.vi}</span>
              </div>
            {/each}
          </div>
        </div>
      {:else if result.example}
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
          <div class="extra-label">Phrasal / Idioms</div>
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
            class:active={result.user_vote === 'up'}
            onclick={() => vote('up')}
            disabled={voteBusy}
            title={result.user_vote === 'up' ? 'Click again to remove your upvote' : 'Worth studying more'}
          >
            👍 {result.up_vote}
          </button>
          <button
            class="vote-btn down"
            class:active={result.user_vote === 'down'}
            onclick={() => vote('down')}
            disabled={voteBusy}
            title={result.user_vote === 'down' ? 'Click again to remove your downvote' : 'I know this already'}
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
        {#if voteError}
          <div class="vote-error">
            {#if voteError.includes('Sign-in') || voteError.includes('401')}
              🔐 Sign in with Google to vote — click 👍/👎 again to retry.
            {:else}
              {voteError}
            {/if}
          </div>
        {/if}
      {/if}
    {:else}
      <!-- Sentence flow: Google Translate gives a Vietnamese translation only.
           No keyword chips, no save UI. To save a specific word from a sentence,
           the user highlights just that word (word flow). See ADR 022. -->
      <header class="sentence-header">
        <h2>{result.text}</h2>
      </header>
      <p class="explanation">{result.explanation}</p>

      {#if result.model_source}
        <div class="model-source-sentence">
          {result.cached ? '⚡ cached' : '✨ fresh'} · {result.model_source}
        </div>
      {/if}
    {/if}
  {/if}
  </div>
</div>
