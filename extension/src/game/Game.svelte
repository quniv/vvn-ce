<script lang="ts">
  import { onMount } from 'svelte'
  import type { PracticeItem } from '../lib/types'
  import { PRACTICE_LIST_KEY } from '../lib/types'
  import Practice from './Practice.svelte'
  import WordBank from './WordBank.svelte'

  type Tab = 'practice' | 'bank'

  // Default tab is Word Bank
  let activeTab = $state<Tab>('bank')
  let practiceKey = $state(0)
  let dueCount = $state(0)

  if (typeof window !== 'undefined') {
    const initial = window.location.hash.replace('#', '') as Tab
    if (initial === 'bank' || initial === 'practice') activeTab = initial
  }

  function setTab(t: Tab) {
    activeTab = t
    if (t === 'practice') practiceKey++
    if (typeof window !== 'undefined') window.location.hash = t
  }

  async function updateDueCount() {
    try {
      const today = new Date().toISOString().slice(0, 10)
      const data = (await chrome.storage.local.get(PRACTICE_LIST_KEY))[PRACTICE_LIST_KEY] as
        | PracticeItem[]
        | undefined
      const list = data ?? []
      dueCount = list.filter(item => item.next_review <= today).length

      // Update Chrome action badge
      if (chrome.action) {
        const text = dueCount > 0 ? String(dueCount) : ''
        await chrome.action.setBadgeText({ text })
        await chrome.action.setBadgeBackgroundColor({ color: '#3b82f6' })
      }
    } catch (e) {
      console.error('Failed to update due count:', e)
    }
  }

  onMount(() => {
    void updateDueCount()
    // Listen for storage changes to update badge in real-time
    const listener = () => void updateDueCount()
    chrome.storage.onChanged.addListener(listener)
    return () => chrome.storage.onChanged.removeListener(listener)
  })
</script>

<main>
  <nav class="tabs">
    <button class:active={activeTab === 'bank'} onclick={() => setTab('bank')}>
      📚 Word Bank
    </button>
    <button class:active={activeTab === 'practice'} onclick={() => setTab('practice')}>
      🧠 Practice
      {#if dueCount > 0}
        <span class="badge">{dueCount}</span>
      {/if}
    </button>
  </nav>

  <div class="content">
    {#if activeTab === 'bank'}
      <WordBank />
    {:else}
      {#key practiceKey}
        <Practice autoStart={true} />
      {/key}
    {/if}
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    background: #0a1020;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    min-height: 100vh;
  }
  main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 24px 24px 48px;
  }
  .tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 24px;
    border-bottom: 1px solid #1e293b;
  }
  .tabs button {
    background: transparent;
    color: #94a3b8;
    border: none;
    padding: 12px 18px;
    cursor: pointer;
    font-family: inherit;
    font-size: 14px;
    font-weight: 500;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }
  .tabs button:hover { color: #e2e8f0; }
  .tabs button.active {
    color: #60a5fa;
    border-bottom-color: #3b82f6;
  }
  .tabs button {
    display: flex;
    align-items: center;
    gap: 8px;
    position: relative;
  }
  .badge {
    background: #3b82f6;
    color: white;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 10px;
    min-width: 20px;
    text-align: center;
    line-height: 1.2;
  }
</style>
