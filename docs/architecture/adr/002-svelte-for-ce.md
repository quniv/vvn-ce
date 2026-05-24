# ADR 002 — Svelte 5 + Vite for Chrome Extension UI

**Status:** Accepted

---

## Context

The Chrome Extension needs three distinct UI surfaces:
- An in-page popup overlay (injected into host pages via content script)
- An options page (for setting the backend URL)
- A game page (full-page matching game, opened in a new tab)

Options considered:

**Option A:** Vanilla JS — no build step, load unpacked instantly, direct DOM manipulation.

**Option B:** React 18 + Vite — component model, large community, many CE tutorials use React.

**Option C:** Svelte 5 + Vite — compiles to vanilla JS at build time, reactive without a runtime library, scoped styles per component.

---

## Decision

**Svelte 5 with a Vite multi-page build** (`@sveltejs/vite-plugin-svelte`).

Entry points are configured in `vite.config.js` as separate Rollup inputs: content script, background (service worker), options page, and game page. Output is written to `extension/dist/` and loaded unpacked in Chrome.

---

## Consequences

**Positive:**
- Svelte compiles away at build time — zero runtime overhead shipped in the extension bundle
- Svelte 5's `$state` rune provides clean reactive state without a virtual DOM
- CSS is scoped per component by default — prevents style bleed between components
- Smallest bundle size among major frameworks for equivalent UI complexity
- Fast iteration: `pnpm build --watch` + reload extension in Chrome

**Negative:**
- Fewer CE-specific tutorials than React (most CE tutorials show React or vanilla JS)
- Svelte 5's runes API (`$state`, `$derived`, `$effect`) is relatively new — existing Svelte 4 examples need adaptation
- Requires a build step; cannot load source files directly as a Chrome Extension

**Risk:** The in-page popup overlay (injected by the content script into arbitrary host pages) is vulnerable to style conflicts — the host page's CSS can override the popup's styles or the popup's styles can leak into the page.

**Mitigation:** The content script attaches the Svelte popup component inside a Shadow DOM root:

```js
// content_script.js
const host = document.createElement('div');
document.body.appendChild(host);
const shadow = host.attachShadow({ mode: 'open' });
// Mount Svelte component into shadow root
new PopupOverlay({ target: shadow, props: { ... } });
```

This adds approximately 20 lines of setup code but fully isolates both the popup's styles from the host page and the host page's styles from the popup. Options and game pages do not need this treatment (they are extension-owned pages, not injected into host pages).
