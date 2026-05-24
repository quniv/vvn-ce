# ADR 003 — Automatic save for words, user-selected save for sentence keywords

**Status:** Accepted

---

## Context

When the user selects text and receives an explanation, should the content be automatically saved to the database? The system handles two fundamentally different input types:

- **Single word** — a discrete vocabulary item the user looked up because they didn't know it
- **Sentence** — a full sentence containing multiple words, some known and some unknown

Options considered:

**Option A:** Auto-save everything — words and all sentence keywords are saved immediately when the backend returns a response.

**Option B:** Never auto-save — always require the user to explicitly confirm what to save, for both words and sentences.

**Option C:** Differentiate by type — words are auto-saved (low noise, always worth saving); sentences return a keyword/chip list and the user selects which ones to save.

---

## Decision

**Option C** — differentiated save flow by input type.

- `type: "word"` → backend auto-saves to DB immediately after explaining, returns explanation JSON
- `type: "sentence"` → backend returns explanation JSON **plus** a `keywords[]` array of identified vocabulary items (phrasal verbs, uncommon words, key terms); backend does NOT save anything; CE shows chips; user selects and explicitly saves chosen ones via `POST /api/words/save`

---

## Consequences

**Positive:**
- Single words are unambiguously new vocabulary — the user selected them specifically because they were unfamiliar; auto-saving is correct and reduces friction
- Sentences contain many words. Some of them (common words, words the user already knows) would pollute the vocabulary list and dilute the end-of-day game with noise
- User maintains curation control over what enters their learning queue from sentences
- The vocabulary database stays high-signal — every word is genuinely unknown to the user

**Negative:**
- Sentence flow requires an extra UI interaction — the user must click chips and click "Save selected" instead of getting automatic saving
- The CE popup must handle two distinct display states (word vs sentence) within a single Svelte component

**Risk:** The user selects a sentence, reads the explanation, then closes the popup without selecting any chips — all identified keywords are lost.

**Mitigation:** The popup stays open until explicitly closed (X button, Esc key, or after the "Saved ✓" confirmation). It does not auto-close on a timer. The "Save selected" button is visually prominent. If the user closes without saving, this is treated as an intentional choice (they may have known all the keywords already).
