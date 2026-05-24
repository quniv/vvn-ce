import { POPUP_THEME_KEY } from '../../lib/types'

export type PopupTheme = 'dark' | 'light' | undefined

export function detectOSTheme(): 'dark' | 'light' {
  if (typeof window === 'undefined' || !window.matchMedia) return 'dark'
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export async function getStoredTheme(): Promise<PopupTheme> {
  const obj = await chrome.storage.local.get(POPUP_THEME_KEY)
  const v = obj[POPUP_THEME_KEY]
  if (v === 'dark' || v === 'light') return v
  return undefined
}

export async function setStoredTheme(t: PopupTheme): Promise<void> {
  if (t === undefined) {
    await chrome.storage.local.remove(POPUP_THEME_KEY)
  } else {
    await chrome.storage.local.set({ [POPUP_THEME_KEY]: t })
  }
}

export function effectiveTheme(stored: PopupTheme): 'dark' | 'light' {
  return stored ?? detectOSTheme()
}
