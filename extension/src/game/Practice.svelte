<script lang="ts">
  import type { PracticeItem } from '../lib/types'
  import { PRACTICE_LIST_KEY } from '../lib/types'

  type View = 'list' | 'flashcard' | 'complete'

  let { autoStart = false }: { autoStart?: boolean } = $props()
  let hasAutoStarted = false

  let practiceList: PracticeItem[] = $state([])
  let view: View = $state('list')
  let currentIndex = $state(0)
  let flipped = $state(false)
  let sessionQueue: PracticeItem[] = $state([])
  let sessionResults: Array<{ id: string; level: 'strong' | 'medium' | 'low' }> = $state([])

  let dueToday: PracticeItem[] = $derived.by(() => {
    const today = new Date().toISOString().slice(0, 10)
    return practiceList.filter(item => item.next_review <= today)
  })

  let upcomingByDate: Map<string, PracticeItem[]> = $derived.by(() => {
    const map = new Map<string, PracticeItem[]>()
    for (const item of practiceList) {
      if (item.next_review > dueToday[0]?.next_review) {
        const date = item.next_review
        if (!map.has(date)) map.set(date, [])
        map.get(date)!.push(item)
      }
    }
    return map
  })

  async function loadPracticeList() {
    try {
      const data = (await chrome.storage.local.get(PRACTICE_LIST_KEY))[PRACTICE_LIST_KEY] as
        | PracticeItem[]
        | undefined
      practiceList = data ?? []
      if (autoStart && !hasAutoStarted && dueToday.length > 0) {
        hasAutoStarted = true
        startSession()
      }
    } catch (e) {
      console.error('Failed to load practice list:', e)
    }
  }

  async function savePracticeList() {
    try {
      await chrome.storage.local.set({ [PRACTICE_LIST_KEY]: practiceList })
    } catch (e) {
      console.error('Failed to save practice list:', e)
    }
  }

  function startSession() {
    if (dueToday.length === 0) return
    sessionQueue = dueToday.map(item => ({ ...item }))
    sessionQueue.sort(() => Math.random() - 0.5)
    currentIndex = 0
    flipped = false
    sessionResults = []
    view = 'flashcard'
  }

  function rate(level: 'strong' | 'medium' | 'low') {
    const current = sessionQueue[currentIndex]
    if (!current) return

    sessionResults.push({ id: current.id, level })

    const today = new Date().toISOString().slice(0, 10)
    let { interval, ease } = current
    if (level === 'strong') {
      interval = Math.max(Math.round(interval * ease), interval + 1)
    } else if (level === 'medium') {
      interval = Math.max(Math.ceil(interval * 1.2), 1)
    } else {
      interval = 1
      ease = Math.max(ease - 0.15, 1.3)
    }

    const nextDate = new Date()
    nextDate.setDate(nextDate.getDate() + interval)
    const nextReview = nextDate.toISOString().slice(0, 10)

    const idx = practiceList.findIndex(item => item.id === current.id)
    if (idx >= 0) {
      practiceList[idx] = {
        ...practiceList[idx],
        interval,
        ease,
        next_review: nextReview,
        last_level: level,
        review_count: practiceList[idx].review_count + 1,
      }
    }

    if (currentIndex < sessionQueue.length - 1) {
      currentIndex++
      flipped = false
    } else {
      void savePracticeList()
      view = 'complete'
    }
  }

  function backToList() {
    view = 'list'
    currentIndex = 0
    flipped = false
    void loadPracticeList()
  }

  $effect.pre(() => {
    void loadPracticeList()
  })
</script>

{#if view === 'list'}
  <div class="practice-container">
    <div class="practice-header">
      <h2>📚 Practice</h2>
      {#if dueToday.length > 0}
        <div class="due-count">{dueToday.length} due today</div>
      {:else}
        <div class="no-due">All caught up!</div>
      {/if}
    </div>

    {#if dueToday.length > 0}
      <div class="due-section">
        <h3>Due Today</h3>
        <div class="due-list">
          {#each dueToday as item (item.id)}
            <div class="due-card">
              <div class="due-text">{item.text}</div>
              <div class="due-meta">
                {#if item.last_level}
                  <span class="due-level" class:strong={item.last_level === 'strong'} class:medium={item.last_level === 'medium'} class:low={item.last_level === 'low'}>
                    {item.last_level}
                  </span>
                {/if}
                <span class="due-interval">interval: {item.interval}d</span>
              </div>
            </div>
          {/each}
        </div>
        <button class="start-btn" onclick={startSession}>Start Session</button>
      </div>
    {/if}

    {#if upcomingByDate.size > 0}
      <div class="upcoming-section">
        <h3>Upcoming</h3>
        {#each upcomingByDate as [date, items]}
          <div class="upcoming-date">
            <div class="date-label">{new Date(date + 'T00:00:00Z').toLocaleDateString()}</div>
            <div class="upcoming-count">{items.length} words</div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
{:else if view === 'flashcard'}
  <div class="flashcard-container">
    <div class="flashcard-header">
      <button class="back-btn" onclick={backToList}>← Back</button>
      <div class="progress">{currentIndex + 1} / {sessionQueue.length}</div>
    </div>

    {#if sessionQueue[currentIndex]}
      <button type="button" class="flashcard" class:flipped onclick={() => (flipped = !flipped)} aria-label="Flip to reveal">
        {#if !flipped}
          <div class="front">
            <div class="word">{sessionQueue[currentIndex].text}</div>
            {#if sessionQueue[currentIndex].word_type || sessionQueue[currentIndex].pronunciation}
              <div class="meta">
                {#if sessionQueue[currentIndex].word_type}
                  <span class="type">{sessionQueue[currentIndex].word_type}</span>
                {/if}
                {#if sessionQueue[currentIndex].pronunciation}
                  <span class="pron">{sessionQueue[currentIndex].pronunciation}</span>
                {/if}
              </div>
            {/if}
            <div class="tap-hint">Tap to reveal</div>
          </div>
        {:else}
          <div class="back">
            <div class="explanation">{sessionQueue[currentIndex].explanation}</div>

            {#if sessionQueue[currentIndex].example}
              <div class="example">"{sessionQueue[currentIndex].example}"</div>
            {/if}

            {#if sessionQueue[currentIndex].vdict_examples?.length}
              {@const examples = sessionQueue[currentIndex].vdict_examples ?? []}
              <div class="vdict-ex">
                <div class="ex-en">{examples[0].en}</div>
                <div class="ex-vi">{examples[0].vi}</div>
              </div>
            {/if}

            {#if sessionQueue[currentIndex].synonyms && sessionQueue[currentIndex].synonyms.length > 0}
              <div class="synonyms">
                {#each sessionQueue[currentIndex].synonyms as syn}
                  <span class="syn-tag">{syn}</span>
                {/each}
              </div>
            {/if}
          </div>
        {/if}
      </button>

      {#if flipped}
        <div class="rating-buttons">
          <button class="rate-btn low" onclick={() => rate('low')}>Low</button>
          <button class="rate-btn medium" onclick={() => rate('medium')}>Medium</button>
          <button class="rate-btn strong" onclick={() => rate('strong')}>Strong</button>
        </div>
      {/if}
    {/if}
  </div>
{:else if view === 'complete'}
  <div class="complete-container">
    <div class="complete-header">
      <h2>🎉 Session Complete!</h2>
    </div>

    <div class="results-stats">
      <div class="stat-item">
        <div class="stat-label">Cards Reviewed</div>
        <div class="stat-value">{sessionResults.length}</div>
      </div>

      <div class="stat-item">
        <div class="stat-label">Strong</div>
        <div class="stat-value strong">
          {sessionResults.filter(r => r.level === 'strong').length}
        </div>
      </div>

      <div class="stat-item">
        <div class="stat-label">Medium</div>
        <div class="stat-value medium">
          {sessionResults.filter(r => r.level === 'medium').length}
        </div>
      </div>

      <div class="stat-item">
        <div class="stat-label">Low</div>
        <div class="stat-value low">
          {sessionResults.filter(r => r.level === 'low').length}
        </div>
      </div>
    </div>

    <button class="back-btn wide" onclick={backToList}>Back to Practice List</button>
  </div>
{/if}

<style>
  .practice-container,
  .flashcard-container,
  .complete-container {
    padding: 20px;
    max-width: 600px;
    margin: 0 auto;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .practice-header {
    margin-bottom: 24px;
  }
  .practice-header h2 {
    margin: 0 0 8px 0;
    font-size: 24px;
    color: #f1f5f9;
  }

  .due-count,
  .no-due {
    font-size: 13px;
    color: #94a3b8;
  }

  .due-section {
    margin-bottom: 32px;
  }
  .due-section h3 {
    margin: 0 0 12px 0;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #64748b;
  }

  .due-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
  }

  .due-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 12px 14px;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
  }
  .due-card:hover {
    background: #111c33;
    border-color: #475569;
  }

  .due-text {
    color: #f1f5f9;
    font-weight: 500;
    margin-bottom: 6px;
  }

  .due-meta {
    display: flex;
    gap: 10px;
    font-size: 12px;
    color: #94a3b8;
  }

  .due-level {
    padding: 2px 8px;
    border-radius: 4px;
    background: #334155;
    text-transform: capitalize;
    font-weight: 500;
  }
  .due-level.strong {
    background: #14532d;
    color: #bbf7d0;
  }
  .due-level.medium {
    background: #713f12;
    color: #fde68a;
  }
  .due-level.low {
    background: #7f1d1d;
    color: #fecaca;
  }

  .due-interval {
    font-family: ui-monospace, monospace;
  }

  .start-btn {
    width: 100%;
    background: #3b82f6;
    color: white;
    border: none;
    padding: 10px 16px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
  }
  .start-btn:hover {
    background: #2563eb;
  }

  .upcoming-section {
    margin-top: 24px;
  }
  .upcoming-section h3 {
    margin: 0 0 12px 0;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #64748b;
  }

  .upcoming-date {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid #334155;
    color: #cbd5e1;
    font-size: 13px;
  }
  .upcoming-date:last-child {
    border-bottom: none;
  }

  .date-label {
    color: #e2e8f0;
  }
  .upcoming-count {
    color: #94a3b8;
    font-size: 12px;
  }

  /* Flashcard view */
  .flashcard-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }

  .back-btn {
    background: transparent;
    color: #3b82f6;
    border: none;
    font-size: 13px;
    cursor: pointer;
    padding: 0;
    font-family: inherit;
  }
  .back-btn:hover {
    text-decoration: underline;
  }
  .back-btn.wide {
    width: 100%;
    background: #1e293b;
    color: #3b82f6;
    border: 1px solid #334155;
    padding: 10px 16px;
    border-radius: 6px;
    font-size: 14px;
    margin-top: 20px;
    transition: background 0.15s;
  }
  .back-btn.wide:hover {
    background: #111c33;
    text-decoration: none;
  }

  .progress {
    font-size: 12px;
    color: #94a3b8;
    font-family: ui-monospace, monospace;
  }

  .flashcard {
    background: #1e293b;
    border: 2px solid #334155;
    border-radius: 12px;
    padding: 40px 24px;
    min-height: 300px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    font-family: inherit;
    font: inherit;
    width: 100%;
  }
  .flashcard:hover {
    border-color: #475569;
  }

  .front,
  .back {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    width: 100%;
    text-align: center;
  }

  .word {
    font-size: 32px;
    font-weight: 600;
    color: #f1f5f9;
    margin-bottom: 8px;
  }

  .meta {
    display: flex;
    justify-content: center;
    gap: 12px;
    flex-wrap: wrap;
    color: #94a3b8;
    font-size: 12px;
  }

  .type {
    background: #334155;
    padding: 2px 8px;
    border-radius: 4px;
    text-transform: capitalize;
  }

  .pron {
    font-family: ui-monospace, monospace;
    color: #cbd5e1;
  }

  .tap-hint {
    margin-top: 16px;
    font-size: 12px;
    color: #64748b;
    font-style: italic;
  }

  .back {
    gap: 12px;
  }

  .explanation {
    color: #e2e8f0;
    font-size: 15px;
    line-height: 1.5;
    margin-bottom: 8px;
    white-space: pre-line;
  }

  .example {
    color: #cbd5e1;
    font-size: 13px;
    font-style: italic;
    padding: 8px 12px;
    background: rgba(51, 65, 85, 0.4);
    border-left: 2px solid #475569;
    border-radius: 4px;
    margin: 8px 0;
  }

  .vdict-ex {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 12px;
    background: rgba(51, 65, 85, 0.4);
    border-radius: 4px;
  }

  .ex-en {
    color: #cbd5e1;
    font-size: 13px;
    font-style: italic;
  }

  .ex-vi {
    color: #94a3b8;
    font-size: 12px;
  }

  .synonyms {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 6px;
    margin-top: 8px;
  }

  .syn-tag {
    background: #334155;
    color: #cbd5e1;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
  }

  .rating-buttons {
    display: flex;
    justify-content: center;
    gap: 12px;
    margin-top: 24px;
  }

  .rate-btn {
    padding: 8px 20px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    border: none;
    cursor: pointer;
    font-family: inherit;
    transition: opacity 0.15s, transform 0.1s;
  }
  .rate-btn:hover {
    transform: scale(1.05);
  }
  .rate-btn:active {
    transform: scale(0.98);
  }

  .rate-btn.low {
    background: #7f1d1d;
    color: #fecaca;
  }
  .rate-btn.medium {
    background: #713f12;
    color: #fde68a;
  }
  .rate-btn.strong {
    background: #14532d;
    color: #bbf7d0;
  }

  /* Complete screen */
  .complete-header {
    text-align: center;
    margin-bottom: 32px;
  }
  .complete-header h2 {
    margin: 0;
    font-size: 28px;
    color: #f1f5f9;
  }

  .results-stats {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-bottom: 32px;
  }

  .stat-item {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
  }

  .stat-label {
    font-size: 12px;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 8px;
    letter-spacing: 0.5px;
  }

  .stat-value {
    font-size: 28px;
    font-weight: 600;
    color: #3b82f6;
  }

  .stat-value.strong {
    color: #bbf7d0;
  }
  .stat-value.medium {
    color: #fde68a;
  }
  .stat-value.low {
    color: #fecaca;
  }
</style>
