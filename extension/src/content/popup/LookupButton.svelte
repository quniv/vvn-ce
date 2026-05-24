<script lang="ts">
  import { effectiveTheme, getStoredTheme } from './theme'

  type Props = {
    onLookup: () => void
  }

  const { onLookup }: Props = $props()

  let theme = $state<'dark' | 'light'>('dark')

  void init()

  async function init() {
    theme = effectiveTheme(await getStoredTheme())
  }

  function handleClick(e: MouseEvent) {
    // Prevent the click from bubbling up to the document mouseup listener,
    // which would otherwise see "click outside selection" and dismiss us
    // before our parent gets the lookup signal.
    e.stopPropagation()
    onLookup()
  }
</script>

<button
  class="lookup-btn theme-{theme}"
  onclick={handleClick}
  onmousedown={(e) => e.stopPropagation()}
  type="button"
>
  🔍 Look up
</button>

<style>
  .lookup-btn {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 13px;
    font-weight: 500;
    padding: 6px 12px;
    border-radius: 999px;
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
    transition: transform 0.1s ease, background 0.15s ease;
    user-select: none;
    -webkit-user-select: none;
    line-height: 1.2;
  }
  .lookup-btn:hover { transform: translateY(-1px); }
  .lookup-btn:active { transform: translateY(0); }

  /* Dark theme (default) */
  .lookup-btn.theme-dark {
    background: rgba(59, 130, 246, 0.95);
    color: white;
    border: 1px solid rgba(96, 165, 250, 0.8);
  }
  .lookup-btn.theme-dark:hover {
    background: rgba(37, 99, 235, 0.98);
  }

  /* Light theme */
  .lookup-btn.theme-light {
    background: rgba(59, 130, 246, 0.95);
    color: white;
    border: 1px solid rgba(37, 99, 235, 0.8);
    box-shadow: 0 4px 14px rgba(59, 130, 246, 0.35);
  }
  .lookup-btn.theme-light:hover {
    background: rgba(37, 99, 235, 0.98);
  }
</style>
