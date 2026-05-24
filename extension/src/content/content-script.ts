import { mount, unmount } from 'svelte'
import Popup from './popup/Popup.svelte'
import popupCss from './popup/Popup.svelte?inline'
import LookupButton from './popup/LookupButton.svelte'
import lookupCss from './popup/LookupButton.svelte?inline'
import type { Message } from '../lib/types'

type ShadowMount = {
  host: HTMLDivElement
  app: ReturnType<typeof mount>
}

let lookupMount: ShadowMount | null = null
let popupMount: ShadowMount | null = null

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
  host.style.position = 'absolute'
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
        showPopup(text, sourceUrl, x, y)
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

function showPopup(text: string, sourceUrl: string, x: number, y: number): void {
  closePopup()
  popupMount = mountInShadow(
    Popup,
    popupCss,
    {
      selectedText: text,
      sourceUrl,
      onClose: closePopup,
      sendMessage: safeSendMessage,
    },
    x,
    y,
  )
}

function getSelectionInfo(): { text: string; x: number; y: number } | null {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) return null
  const text = selection.toString().trim()
  if (!text) return null
  const range = selection.getRangeAt(0)
  const rect = range.getBoundingClientRect()
  return {
    text,
    x: window.scrollX + rect.left,
    y: window.scrollY + rect.bottom + 8,
  }
}

document.addEventListener('mouseup', (e) => {
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
