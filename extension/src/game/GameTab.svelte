<script lang="ts">
  // Practice tab placeholder. The matching game was disabled in Phase 6;
  // the next CR (Phase 7) will replace this with a Spaced Repetition flow —
  // see docs/architecture/adr/019-spaced-repetition-design.md.
</script>

<section>
  <header>
    <h2>🧠 Practice</h2>
  </header>

  <div class="card">
    <h3>Spaced Repetition coming soon</h3>
    <p>
      The matching game was disabled in favour of a proper Spaced Repetition workflow
      (SM-2 algorithm — the same one Anki uses). Each saved word will be scheduled for
      review at scientifically-motivated intervals so you actually retain what you look up.
    </p>
    <p>
      The full design is documented in
      <code>docs/architecture/adr/019-spaced-repetition-design.md</code> and will be
      implemented in the next change.
    </p>
    <div class="planned">
      <strong>What's planned:</strong>
      <ul>
        <li>Daily queue of due words, ordered by oldest due first</li>
        <li>Flashcard UI — see the word, click to reveal the explanation</li>
        <li>Four rating buttons: Again · Hard · Good · Easy</li>
        <li>SM-2 algorithm updates interval / ease / next due date</li>
      </ul>
    </div>
    <p class="hint">
      In the meantime, use the <strong>Word Bank</strong> tab to browse all words you've
      looked up. Highlight any text on a webpage to add new ones.
    </p>
  </div>
</section>

<style>
  section { display: flex; flex-direction: column; gap: 14px; }
  header {
    display: flex; justify-content: space-between; align-items: baseline;
    flex-wrap: wrap; gap: 12px;
  }
  h2 { margin: 0; font-size: 22px; color: #f1f5f9; }
  .card {
    background: #111c33;
    border: 1px solid #1e293b;
    padding: 24px 28px;
    border-radius: 14px;
    color: #cbd5e1;
  }
  h3 {
    margin: 0 0 12px;
    color: #f1f5f9;
    font-size: 17px;
  }
  p {
    margin: 0 0 12px;
    font-size: 14px;
    line-height: 1.6;
  }
  code {
    background: #0f1729;
    padding: 1px 6px;
    border-radius: 4px;
    font-family: ui-monospace, monospace;
    font-size: 12px;
    color: #93c5fd;
  }
  .planned {
    background: #0f1729;
    padding: 14px 18px;
    border-radius: 10px;
    margin: 16px 0;
    font-size: 13px;
  }
  .planned strong { color: #f1f5f9; }
  .planned ul { margin: 8px 0 0; padding-left: 20px; line-height: 1.7; }
  .hint {
    color: #64748b;
    font-size: 13px;
    margin-top: 18px;
  }
</style>
