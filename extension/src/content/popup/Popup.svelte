<script lang="ts">
  import type {
    ExplainResponse,
    ExplainResult,
    Message,
    PracticeItem,
  } from "../../lib/types";
  import { PRACTICE_LIST_KEY } from "../../lib/types";
  import { effectiveTheme, getStoredTheme, setStoredTheme } from "./theme";
  import Fireworks from "./Fireworks.svelte";

  type Props = {
    selectedText: string;
    sourceUrl: string;
    onClose: () => void;
    sendMessage: (msg: Message) => Promise<unknown>;
    onMove?: (newX: number, newY: number) => void;
    getPosition?: () => { x: number; y: number };
    onDragStart?: () => void;
    onDragEnd?: () => void;
    onResizeStart?: () => void;
    onResizeEnd?: () => void;
    onResize?: (newW: number, newH: number) => void;
    getSize?: () => { w: number; h: number };
  };

  const {
    selectedText,
    sourceUrl,
    onClose,
    sendMessage,
    onMove,
    getPosition,
    onDragStart,
    onDragEnd,
    onResizeStart,
    onResizeEnd,
    onResize,
    getSize,
  }: Props = $props();

  let dragStart: {
    mouseX: number;
    mouseY: number;
    hostX: number;
    hostY: number;
  } | null = null;
  let resizeStart: {
    mouseX: number;
    mouseY: number;
    startW: number;
    startH: number;
  } | null = null;

  function handleDragStart(e: MouseEvent) {
    if (!onMove || !getPosition) return;
    e.preventDefault();
    const pos = getPosition();
    dragStart = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      hostX: pos.x,
      hostY: pos.y,
    };
    onDragStart?.();
    window.addEventListener("mousemove", handleDragMove);
    window.addEventListener("mouseup", handleDragEnd);
  }

  function handleDragMove(e: MouseEvent) {
    if (!dragStart || !onMove) return;
    const size = getSize?.();
    if (!size) return;

    // const newX = dragStart.hostX + (e.clientX - dragStart.mouseX);
    // const newY = dragStart.hostY + (e.clientY - dragStart.mouseY);
    const newX = dragStart.hostX + (e.clientX - dragStart.mouseX);
    const newY = dragStart.hostY + (e.clientY - dragStart.mouseY);

    const clampedX = Math.max(0, Math.min(newX, window.innerWidth - size.w));
    const clampedY = Math.max(0, Math.min(newY, window.innerHeight - size.h));

    onMove(clampedX, clampedY);
  }

  function handleDragEnd() {
    dragStart = null;
    onDragEnd?.();
    window.removeEventListener("mousemove", handleDragMove);
    window.removeEventListener("mouseup", handleDragEnd);
  }

  function handleResizeStart(e: MouseEvent) {
    if (!onResize || !getSize) return;
    e.preventDefault();
    const size = getSize();
    resizeStart = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      startW: size.w,
      startH: size.h,
    };
    onResizeStart?.();
    window.addEventListener("mousemove", handleResizeMove);
    window.addEventListener("mouseup", handleResizeEnd);
  }

  function handleResizeMove(e: MouseEvent) {
    if (!resizeStart || !onResize) return;
    const deltaX = e.clientX - resizeStart.mouseX;
    const deltaY = e.clientY - resizeStart.mouseY;
    const newW = Math.max(280, resizeStart.startW + deltaX);
    const newH = Math.max(350, resizeStart.startH + deltaY);
    onResize(newW, newH);
  }

  function handleResizeEnd() {
    resizeStart = null;
    onResizeEnd?.();
    window.removeEventListener("mousemove", handleResizeMove);
    window.removeEventListener("mouseup", handleResizeEnd);
  }

  let loading = $state(true);
  let error = $state<string | null>(null);
  let result = $state<ExplainResponse | null>(null);
  let theme = $state<"dark" | "light">("dark");
  let inPractice = $state(false);
  let showingFireworks = $state(false);

  type WordTab = 'meaning' | 'examples' | 'synonyms' | 'phrasal'
  let activeTab = $state<WordTab>('meaning')

  // Init theme + kick off the fetch once when the component is created
  void initTheme();
  void fetchExplain();

  async function initTheme() {
    theme = effectiveTheme(await getStoredTheme());
  }

  async function toggleTheme() {
    const next: "dark" | "light" = theme === "dark" ? "light" : "dark";
    theme = next;
    await setStoredTheme(next);
  }

  async function fetchExplain() {
    loading = true;
    error = null;
    try {
      const res = (await sendMessage({
        type: "EXPLAIN",
        payload: { text: selectedText, source_url: sourceUrl },
      })) as ExplainResult;
      if (!res.ok) {
        error = res.error;
      } else {
        result = res.data;
        await checkInPractice();
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function checkInPractice() {
    if (!result || !result.saved_id) return;
    try {
      const items = (await chrome.storage.local.get(PRACTICE_LIST_KEY))[
        PRACTICE_LIST_KEY
      ] as PracticeItem[] | undefined;
      inPractice =
        Array.isArray(items) &&
        items.some((item) => item.id === result!.saved_id);
    } catch (e) {
      console.error("Failed to check practice list:", e);
    }
  }

  async function addToPractice() {
    if (!result || !result.saved_id || inPractice) return;
    try {
      const today = new Date().toISOString().slice(0, 10);
      const items = (await chrome.storage.local.get(PRACTICE_LIST_KEY))[
        PRACTICE_LIST_KEY
      ] as PracticeItem[] | undefined;
      const practiceList = items ?? [];

      const newItem: PracticeItem = {
        id: result.saved_id,
        text: result.text,
        word_type: result.word_type,
        pronunciation: result.pronunciation,
        explanation: result.explanation,
        example: result.example,
        synonyms: result.synonyms ?? [],
        collocations: result.collocations ?? [],
        difficulty: result.difficulty,
        audio_url: result.audio_url,
        vdict_examples: result.vdict_examples,
        added_at: new Date().toISOString(),
        next_review: today,
        interval: 1,
        ease: 2.5,
        review_count: 0,
        last_level: null,
      };

      practiceList.push(newItem);
      await chrome.storage.local.set({ [PRACTICE_LIST_KEY]: practiceList });

      inPractice = true;
      showingFireworks = true;

      setTimeout(() => {
        showingFireworks = false;
      }, 1500);
    } catch (e) {
      console.error("Failed to add to practice:", e);
    }
  }
</script>

{#if showingFireworks}
  <Fireworks onDone={() => {}} />
{/if}

<div class="card theme-{theme}" role="dialog">
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="drag-handle"
    role="separator"
    aria-label="Move card"
    onmousedown={handleDragStart}
  >
    ⠿
  </div>
  <div class="header-buttons">
    {#if result?.saved && result.saved_id && result.kind === "word"}
      <button
        class="add-to-learn-btn"
        onclick={addToPractice}
        disabled={inPractice}
        title={inPractice
          ? "Already in practice"
          : "Add this word to your practice list"}
      >
        {inPractice ? "✓ In practice" : "+ Practice"}
      </button>
    {/if}
    <button class="theme-btn" aria-label="Toggle theme" onclick={toggleTheme}>
      {theme === "dark" ? "☀️" : "🌙"}
    </button>
  </div>
  <button class="close" aria-label="Close" onclick={onClose}>×</button>
  <button
    class="resize-btn"
    aria-label="Resize card"
    onmousedown={handleResizeStart}
    title="Drag to resize">⤡</button
  >

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
      {#if result.kind === "word"}
        <header class="word-header">
          <h1>{result.text}</h1>
          {#if result.word_type}
            <span class="badge">{result.word_type}</span>
          {/if}
          {#if result.difficulty}
            <span class="badge difficulty difficulty-{result.difficulty}"
              >{result.difficulty}</span
            >
          {/if}
          {#if result.pronunciation}
            <span class="pron">{result.pronunciation}</span>
          {/if}
          {#if result.audio_url}
            <button
              class="audio-btn"
              aria-label="Play pronunciation"
              onclick={() => new Audio(result!.audio_url!).play()}>▶</button
            >
          {/if}
        </header>

        <!-- Tab bar -->
        <nav class="word-tabs">
          <button
            class="tab-btn"
            class:active={activeTab === 'meaning'}
            onclick={() => activeTab = 'meaning'}
          >Meaning</button>
          <button
            class="tab-btn"
            class:active={activeTab === 'examples'}
            onclick={() => activeTab = 'examples'}
          >Examples</button>
          {#if result.synonyms && result.synonyms.length > 0}
            <button
              class="tab-btn"
              class:active={activeTab === 'synonyms'}
              onclick={() => activeTab = 'synonyms'}
            >Synonyms</button>
          {/if}
          {#if result.collocations && result.collocations.length > 0}
            <button
              class="tab-btn"
              class:active={activeTab === 'phrasal'}
              onclick={() => activeTab = 'phrasal'}
            >Phrasal / Idioms</button>
          {/if}
        </nav>

        <!-- Tab panels -->
        <div class="tab-panel">
          {#if activeTab === 'meaning'}
            {#if result.meanings && result.meanings.length > 0}
              {#each result.meanings as group}
                {#if group.pos}
                  <div class="pos-label">{group.pos}</div>
                {/if}
                <ul class="meaning-list">
                  {#each group.items as item}
                    <li>
                      <span class="meaning-vi">{item.vi}</span>
                      {#if item.description}
                        <span class="meaning-desc">: {item.description}</span>
                      {/if}
                    </li>
                  {/each}
                </ul>
              {/each}
            {:else}
              <p class="explanation">{result.explanation}</p>
            {/if}
          {:else if activeTab === 'examples'}
            {#if result.vdict_examples && result.vdict_examples.length > 0}
              <div class="example-pairs">
                {#each result.vdict_examples as ex, i (i)}
                  <div class="example-pair">
                    <span class="ex-en">{ex.en}</span>
                    <span class="ex-vi">{ex.vi}</span>
                  </div>
                {/each}
              </div>
            {:else if result.example}
              <p class="example">"<em>{result.example}</em>"</p>
            {:else}
              <p class="tab-empty">No examples available.</p>
            {/if}
          {:else if activeTab === 'synonyms'}
            <div class="syn-chips">
              {#each result.synonyms ?? [] as s, i (i)}
                <span class="syn-chip">{s}</span>
              {/each}
            </div>
          {:else if activeTab === 'phrasal'}
            <ul class="colloc-list">
              {#each result.collocations ?? [] as c, i (i)}
                <li>{c}</li>
              {/each}
            </ul>
          {/if}
        </div>
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
            {result.cached ? "⚡ cached" : "✨ fresh"} · {result.model_source}
          </div>
        {/if}
      {/if}
    {/if}
  </div>
</div>
