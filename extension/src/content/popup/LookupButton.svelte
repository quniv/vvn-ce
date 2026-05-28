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
