# ADR-014: Gate the LLM Call Behind a "Look Up" Click

## Status
Accepted

## Context

Previously, every `mouseup` with a non-empty selection auto-mounted the full popup, which immediately fired `POST /api/explain`. In practice this is too eager:

- Users select text for many reasons that have nothing to do with vocabulary (copy, drag, re-reading).
- Each unwanted call costs an LLM round-trip (latency, free-tier rate-limit / paid token spend).
- Each word that returns becomes a row in the `words` table (now deduped, but still pollutes the bank).

The popup auto-mount also stole the user's attention in the middle of reading flow — distracting on long-form pages.

## Decision

Insert a **gating step**: on `mouseup` with a non-empty selection, the content script mounts a small floating button ("🔍 Look up") in a Shadow DOM host positioned at the selection's bottom-left. The full Popup mounts only after the user clicks the button.

**Dismissal:**
- Click the button → mount Popup, remove button
- New selection elsewhere → remove old button, mount new button at new position
- Click outside the button (with no fresh selection) → remove button
- Esc → remove both button and popup

**Code shape:**
- New file: `extension/src/content/popup/LookupButton.svelte`
- `content-script.ts` is refactored: the existing `showPopup(text, x, y)` is now called only from the button's `onLookup` callback, not directly on `mouseup`.
- A shared "mount in Shadow DOM at (x, y)" helper is extracted to avoid duplicating the host + Shadow + style-injection boilerplate.

## Consequences

**Positive:**
- Zero LLM calls from incidental selections.
- The Word Bank now contains only words the user explicitly looked up.
- Reading flow is not interrupted by unsolicited popups.
- Visible affordance ("🔍 Look up") makes the feature discoverable — new users see it and know what the extension does.

**Negative / trade-offs:**
- Every lookup now requires one extra click. For habitual users this is a small but non-zero friction.
- The Look-up button itself is a new in-page element, so it needs its own theming and dismissal logic.

**Risks:**
- **Keyboard-only selections (Shift+Arrow) never produce `mouseup`** and so never trigger the button. The previous implementation had the same limitation — no regression. If keyboard support is added later, listen to `selectionchange` (debounced) and mount the button on the new selection.
- **Race condition between dismissal and click**: if the user clicks "Look up" simultaneously with another mouseup, the new mouseup could remove the button. Mitigation: the click handler stops propagation and removes the button itself before invoking the popup mount, so the subsequent mouseup sees no host to remove.

## Notes

Future enhancement (out of scope): a keyboard shortcut (e.g. `Cmd+Shift+L`) that triggers the look-up flow on the current selection without requiring the button click — useful for power users.
