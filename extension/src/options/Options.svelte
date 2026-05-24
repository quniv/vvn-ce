<script lang="ts">
  import { DEFAULT_BACKEND_URL } from '../lib/types'

  let backendUrl = $state(DEFAULT_BACKEND_URL)
  let status = $state<'idle' | 'saved'>('idle')
  let loaded = $state(false)

  void loadSettings()

  async function loadSettings() {
    const { backendUrl: stored } = await chrome.storage.local.get('backendUrl')
    if (stored) backendUrl = stored as string
    loaded = true
  }

  async function save() {
    await chrome.storage.local.set({ backendUrl: backendUrl.trim() || DEFAULT_BACKEND_URL })
    status = 'saved'
    setTimeout(() => (status = 'idle'), 1500)
  }

  async function testConnection() {
    try {
      const res = await fetch(`${backendUrl.trim().replace(/\/$/, '')}/api/health`)
      if (res.ok) alert('Backend OK: ' + JSON.stringify(await res.json()))
      else alert(`Backend returned ${res.status}`)
    } catch (e) {
      alert('Cannot reach backend: ' + (e instanceof Error ? e.message : String(e)))
    }
  }
</script>

<main>
  <h1>Vocab CE Options</h1>
  {#if loaded}
    <label>
      <span>Backend URL</span>
      <input type="url" bind:value={backendUrl} placeholder={DEFAULT_BACKEND_URL} />
    </label>

    <div class="actions">
      <button onclick={save} class="primary">Save</button>
      <button onclick={testConnection}>Test connection</button>
      {#if status === 'saved'}
        <span class="status">Saved ✓</span>
      {/if}
    </div>

    <p class="hint">
      The backend handles all OpenRouter calls and chooses the LLM model itself. To change the model,
      edit <code>backend/.env</code> (variable <code>OPENROUTER_MODEL</code>) and recreate the api
      container.
    </p>
  {:else}
    <p>Loading…</p>
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    background: #0f1729;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    min-height: 100vh;
  }
  main {
    max-width: 560px;
    margin: 40px auto;
    padding: 24px 32px;
    background: #111c33;
    border: 1px solid #1e293b;
    border-radius: 14px;
  }
  h1 {
    margin: 0 0 18px;
    font-size: 22px;
    color: #f1f5f9;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 18px;
  }
  label span {
    font-size: 13px;
    color: #94a3b8;
  }
  input[type="url"] {
    background: #0f1729;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding: 10px 12px;
    border-radius: 8px;
    font-size: 14px;
    font-family: inherit;
  }
  input:focus {
    outline: none;
    border-color: #3b82f6;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
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
  button.primary {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }
  button.primary:hover { background: #2563eb; }
  .status { color: #4ade80; font-size: 13px; }
  .hint {
    margin-top: 18px;
    color: #64748b;
    font-size: 12px;
    line-height: 1.6;
  }
  code {
    background: #0f1729;
    padding: 1px 6px;
    border-radius: 4px;
    font-family: ui-monospace, monospace;
  }
</style>
