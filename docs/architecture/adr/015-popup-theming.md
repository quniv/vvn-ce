# ADR-015: Popup Theming (Auto + Manual Override), No Border, 90% Opacity Background

## Status
Accepted

## Context

The popup was hard-coded to a dark theme with a fixed `#1e293b` border. Two problems:

1. **No light mode.** Users on light-mode operating systems / light webpages saw a heavy dark card that did not feel native.
2. **The border felt heavy** on top of varied webpage backgrounds — particularly busy ones — and contributed nothing to readability beyond what a soft shadow already provided.

## Decision

Implement a dual-theme popup with three layers of control:

1. **Auto-detect by default** — CSS `@media (prefers-color-scheme: light)` inside the Shadow DOM stylesheet flips the palette automatically. No user action required.
2. **Manual override** — a small toggle button in the popup header (🌙 in light, ☀️ in dark — shows the theme it switches TO) flips the active theme. The choice is persisted in `chrome.storage.local.popupTheme` (`'dark' | 'light' | undefined`). When set, it overrides the OS preference for all subsequent popups.
3. **CSS hook** — a class on the card root (`theme-dark` or `theme-light`) takes precedence over the media query when present, so the override is deterministic.

**Visual changes:**
- The 1px border is **removed**. The card relies on its drop shadow (existing `box-shadow: 0 10px 32px rgba(0, 0, 0, 0.5)` in dark; softer shadow in light) for separation from the page.
- Background uses `rgba(...)` at **90% opacity** (dark: `rgba(15, 23, 41, 0.9)`; light: `rgba(255, 255, 255, 0.92)`), giving a faint translucency to the page underneath.

**Shared helpers** live in `extension/src/content/popup/theme.ts`:
- `PopupTheme = 'dark' | 'light' | undefined`
- `detectOSTheme()` — `window.matchMedia('(prefers-color-scheme: light)').matches`
- `getStoredTheme() / setStoredTheme()` — `chrome.storage.local.popupTheme`
- `effectiveTheme(stored)` — `stored ?? detectOSTheme()`

Both the Look-up button and the Popup read this on mount and apply the resulting class.

## Consequences

**Positive:**
- The popup feels native on both light and dark systems out of the box.
- The user retains control via a one-click toggle that persists across sessions.
- A slightly translucent card looks lighter on the page and lets the surrounding content remain just visible — better visual continuity.
- The theme module is testable in isolation; both components share one implementation.

**Negative / trade-offs:**
- Every coloured CSS rule in `Popup.svelte` now has a light-mode counterpart — ~30 rules. The audit is one-time but tedious.
- `prefers-color-scheme` is a system-level signal; if the user switches OS theme while a popup is open, the popup will not flip until the next mount. Acceptable for a tool used in short bursts.

**Risks:**
- **Storage write conflict** if multiple popups try to update `popupTheme` at the same time. Realistically only one popup is open at a time; harmless even if it happened.
- **Shadow DOM media query.** `@media (prefers-color-scheme: ...)` does work inside Shadow DOM (it references the parent window). If a future Chrome change breaks this, the explicit class fallback still works because the toggle button writes it.

## Notes

The toggle button position is the top-right of the card, immediately left of the existing close (×) button. Keyboard accessibility: `aria-label="Toggle theme"`; works with Tab + Enter.

Future enhancement (out of scope): an "Auto" option in the toggle that explicitly resets `chrome.storage.local.popupTheme` to `undefined`. Today, "auto" is the implicit default state; a user who manually flipped once can clear the override via DevTools or by reinstalling the extension. Acceptable since most users will pick one mode and stick with it.
