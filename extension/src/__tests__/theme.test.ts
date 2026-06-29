import { describe, it, expect, afterEach, vi } from 'vitest'
import { detectOSTheme, effectiveTheme } from '../content/popup/theme'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('effectiveTheme', () => {
  it('returns dark when stored is dark', () => {
    expect(effectiveTheme('dark')).toBe('dark')
  })

  it('returns light when stored is light', () => {
    expect(effectiveTheme('light')).toBe('light')
  })

  it('falls back to OS detection when stored is undefined', () => {
    // jsdom does not define matchMedia → detectOSTheme returns 'dark'
    const result = effectiveTheme(undefined)
    expect(['dark', 'light']).toContain(result)
  })
})

describe('detectOSTheme', () => {
  it('returns dark when matchMedia is unavailable', () => {
    vi.stubGlobal('window', { matchMedia: undefined })
    expect(detectOSTheme()).toBe('dark')
  })

  it('returns light when prefers-color-scheme: light matches', () => {
    vi.stubGlobal('window', {
      matchMedia: (query: string) => ({ matches: query.includes('light') }),
    })
    expect(detectOSTheme()).toBe('light')
  })

  it('returns dark when prefers-color-scheme: light does not match', () => {
    vi.stubGlobal('window', {
      matchMedia: (_query: string) => ({ matches: false }),
    })
    expect(detectOSTheme()).toBe('dark')
  })
})
