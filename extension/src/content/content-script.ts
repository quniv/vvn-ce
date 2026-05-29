import { mount, unmount } from 'svelte'
import Popup from './popup/Popup.svelte'
import popupCss from './popup/Popup.css?inline'
import LookupButton from './popup/LookupButton.svelte'
import lookupCss from './popup/LookupButton.css?inline'
import type { Message } from '../lib/types'

type ShadowMount = {
  host: HTMLDivElement
  app: ReturnType<typeof mount>
}

let lookupMount: ShadowMount | null = null
let popupMount: ShadowMount | null = null
let dragging = false
let resizing = false

function getDefaultPopupWidth(): number {
  const screenWidth = window.innerWidth
  // On mobile: ~90% of screen, on desktop: ~25% but max 450px, min 280px
  const width = Math.min(450, Math.max(280, screenWidth * 0.8))
  return Math.round(width)
}

let popupSize = { w: getDefaultPopupWidth(), h: 400 }

/**
 * Mount a Svelte component inside a Shadow DOM host positioned at (x, y).
 * Returns the host + Svelte app handle so callers can clean up.
 */
function mountInShadow(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Component: any,
  css: string,
  props: Record<string, unknown>,
  x: number,
  y: number,
): ShadowMount {
  const host = document.createElement('div')
  host.style.position = 'fixed'
  host.style.left = `${x}px`
  host.style.top = `${y}px`
  host.style.zIndex = '2147483647'
  host.style.pointerEvents = 'auto'
  document.body.appendChild(host)

  const shadow = host.attachShadow({ mode: 'closed' })

  const style = document.createElement('style')
  style.textContent = css
  shadow.appendChild(style)

  const mountPoint = document.createElement('div')
  shadow.appendChild(mountPoint)

  const app = mount(Component, { target: mountPoint, props })
  return { host, app }
}

function closeMount(m: ShadowMount | null): void {
  if (!m) return
  try {
    unmount(m.app)
  } catch {
    /* ignore */
  }
  m.host.remove()
}

function closeLookup(): void {
  closeMount(lookupMount)
  lookupMount = null
}

function closePopup(): void {
  closeMount(popupMount)
  popupMount = null
}

function closeAll(): void {
  closeLookup()
  closePopup()
}

function isHostNode(host: HTMLElement | null | undefined, target: EventTarget | null): boolean {
  return !!host && !!target && host.contains(target as Node)
}

function showLookupButton(text: string, sourceUrl: string, x: number, y: number): void {
  closeLookup()
  closePopup()

  lookupMount = mountInShadow(
    LookupButton,
    lookupCss,
    {
      onLookup: () => {
        closeLookup()
        showPopup(text, sourceUrl)
      },
    },
    x,
    y,
  )
}

function safeSendMessage(msg: Message): Promise<unknown> {
  // `chrome.runtime` can become undefined if the extension was reloaded while
  // this content script remained injected. Surface a clear error instead of
  // the cryptic "Cannot read properties of undefined (reading 'sendMessage')".
  if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.sendMessage) {
    return Promise.reject(
      new Error('Extension was reloaded — please refresh this page (F5)'),
    )
  }
  return chrome.runtime.sendMessage(msg)
}

async function savePopupSize(w: number, h: number): Promise<void> {
  popupSize = { w, h }
  await chrome.storage.local.set({ popupSize })
}

function showPopup(text: string, sourceUrl: string): void {
  closePopup()

  const x = Math.max(0, (window.innerWidth - popupSize.w) / 2)
  const y = Math.max(0, (window.innerHeight - popupSize.h) / 3)

  const host = document.createElement('div')
  host.style.position = 'fixed'
  host.style.left = `${x}px`
  host.style.top = `${y}px`
  host.style.height = `${popupSize.h}px`
  host.style.width = `${popupSize.w}px`
  host.style.zIndex = '2147483647'
  host.style.pointerEvents = 'auto'
  document.body.appendChild(host)

  const shadow = host.attachShadow({ mode: 'closed' })
  const styleEl = document.createElement('style')
  styleEl.textContent = popupCss
  shadow.appendChild(styleEl)
  const mountPoint = document.createElement('div')
  shadow.appendChild(mountPoint)

  const app = mount(Popup, {
    target: mountPoint,
    props: {
      selectedText: text,
      sourceUrl,
      onClose: closePopup,
      sendMessage: safeSendMessage,
      onDragStart: () => { dragging = true },
      onDragEnd: () => { dragging = false },
      onMove: (newX: number, newY: number) => {
        host.style.left = `${newX}px`
        host.style.top = `${newY}px`
      },
      getPosition: () => ({
        x: parseInt(host.style.left, 10),
        y: parseInt(host.style.top, 10),
      }),
      onResizeStart: () => { resizing = true },
      onResizeEnd: () => { resizing = false },
      onResize: (newW: number, newH: number) => {
        host.style.width = `${newW}px`
        savePopupSize(newW, newH).catch(console.error)
      },
      getSize: () => popupSize,
    },
  })
  popupMount = { host, app }
}

function getSelectionInfo(): { text: string; x: number; y: number } | null {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) return null
  const text = selection.toString().trim()
  if (!text) return null
  const range = selection.getRangeAt(0)
  const rect = range.getBoundingClientRect()

  // Estimated button dimensions (🔍 Look up, font 13px, padding 6px 12px)
  const BTN_W = 84
  const BTN_H = 32
  const GAP = 6

  // Anchor: top-right of the selection (right-aligned, above)
  let left = rect.right - BTN_W
  let top = rect.top - BTN_H - GAP

  // If button would clip above the viewport, show it below instead
  if (top < 4) top = rect.bottom + GAP

  // If button right edge would clip the viewport right, shift left
  if (rect.right > window.innerWidth - 8) left = window.innerWidth - BTN_W - 8

  // Never go off the left edge
  if (left < 8) left = 8

  return {
    text,
    x: left,
    y: top,
  }
}

document.addEventListener('mouseup', (e) => {
  if (dragging || resizing) return
  // Ignore clicks inside our own UI
  if (isHostNode(lookupMount?.host ?? null, e.target)) return
  if (isHostNode(popupMount?.host ?? null, e.target)) return

  const info = getSelectionInfo()

  if (!info) {
    // No selection — treat as a click-outside dismissal
    if (lookupMount || popupMount) closeAll()
    return
  }

  // New non-empty selection — show the look-up button (popup mounts only on click)
  showLookupButton(info.text, window.location.href, info.x, info.y)
})

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeAll()
})
