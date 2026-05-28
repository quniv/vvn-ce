<script lang="ts">
  import GameTab from './GameTab.svelte'
  import WordBank from './WordBank.svelte'

  type Tab = 'practice' | 'bank'

  // Default tab is now Word Bank (game is disabled — Spaced Repetition coming, see ADR 019)
  let activeTab = $state<Tab>('bank')

  if (typeof window !== 'undefined') {
    const initial = window.location.hash.replace('#', '') as Tab
    if (initial === 'bank' || initial === 'practice') activeTab = initial
  }

  function setTab(t: Tab) {
    activeTab = t
    if (typeof window !== 'undefined') window.location.hash = t
  }
</script>

<main>
  <nav class="tabs">
    <button class:active={activeTab === 'bank'} onclick={() => setTab('bank')}>
      📚 Word Bank
    </button>
    <button class:active={activeTab === 'practice'} onclick={() => setTab('practice')}>
      🧠 Practice
    </button>
  </nav>

  <div class="content">
    {#if activeTab === 'bank'}
      <WordBank />
    {:else}
      <GameTab />
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
</style>
