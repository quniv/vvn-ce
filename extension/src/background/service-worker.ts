import {
  DEFAULT_BACKEND_URL,
  WORDBANK_STORAGE_KEY,
  WORDBANK_SYNCED_AT_KEY,
  WORDBANK_SYNC_ERROR_KEY,
  type ExplainResult,
  type Message,
  type SaveResult,
  type WordBankResponse,
  type WordRead,
} from '../lib/types'

const WORDBANK_SYNC_ALARM = 'syncWordBank'
const WORDBANK_SYNC_PERIOD_MINUTES = 5

async function getBackendUrl(): Promise<string> {
  const { backendUrl } = await chrome.storage.local.get('backendUrl')
  return (backendUrl as string) || DEFAULT_BACKEND_URL
}

/**
 * Wraps chrome.identity.getAuthToken. Returns null instead of throwing —
 * callers decide whether absence of a token is fatal (VOTE) or fine (listings).
 */
function getAccessToken(interactive: boolean): Promise<string | null> {
  return new Promise((resolve) => {
    try {
      chrome.identity.getAuthToken({ interactive }, (token) => {
        if (chrome.runtime.lastError || !token) {
          resolve(null)
          return
        }
        resolve(typeof token === 'string' ? token : (token as { token?: string }).token ?? null)
      })
    } catch {
      resolve(null)
    }
  })
}

async function authHeaders(interactive: boolean): Promise<Record<string, string>> {
  const token = await getAccessToken(interactive)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function syncWordBank(): Promise<WordBankResponse> {
  const backendUrl = await getBackendUrl()
  const auth = await authHeaders(false)
  try {
    const res = await fetch(`${backendUrl}/api/words?limit=1000`, { headers: auth })
    if (!res.ok) {
      const text = await res.text()
      const error = `Backend ${res.status}: ${text.slice(0, 200)}`
      await chrome.storage.local.set({ [WORDBANK_SYNC_ERROR_KEY]: error })
      return { ok: false, error }
    }
    const data = (await res.json()) as WordRead[]
    const syncedAt = new Date().toISOString()
    await chrome.storage.local.set({
      [WORDBANK_STORAGE_KEY]: data,
      [WORDBANK_SYNCED_AT_KEY]: syncedAt,
      [WORDBANK_SYNC_ERROR_KEY]: null,
    })
    return { ok: true, data, syncedAt }
  } catch (e) {
    const error = `Network error: ${e instanceof Error ? e.message : String(e)}`
    await chrome.storage.local.set({ [WORDBANK_SYNC_ERROR_KEY]: error })
    return { ok: false, error }
  }
}

function triggerSync(): void {
  syncWordBank().catch((e) => console.warn('[vvn-ce] background sync failed', e))
}

async function handleExplain(payload: { text: string; source_url?: string }): Promise<ExplainResult> {
  const backendUrl = await getBackendUrl()
  const auth = await authHeaders(false) // non-interactive — listings still work without sign-in
  try {
    const res = await fetch(`${backendUrl}/api/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...auth },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const text = await res.text()
      return { ok: false, error: `Backend ${res.status}: ${text.slice(0, 200)}` }
    }
    const data = await res.json()
    triggerSync()
    return { ok: true, data }
  } catch (e) {
    return { ok: false, error: `Network error: ${e instanceof Error ? e.message : String(e)}` }
  }
}

async function handleSaveKeywords(payload: {
  source_sentence: string
  source_url?: string
  keywords: unknown[]
}): Promise<SaveResult> {
  const backendUrl = await getBackendUrl()
  const auth = await authHeaders(false)
  try {
    const res = await fetch(`${backendUrl}/api/words/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...auth },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const text = await res.text()
      return { ok: false, error: `Backend ${res.status}: ${text.slice(0, 200)}` }
    }
    triggerSync()
    return { ok: true }
  } catch (e) {
    return { ok: false, error: `Network error: ${e instanceof Error ? e.message : String(e)}` }
  }
}

chrome.runtime.onMessage.addListener((msg: Message, _sender, sendResponse) => {
  if (msg.type === 'EXPLAIN') {
    handleExplain(msg.payload).then(sendResponse)
    return true
  }
  if (msg.type === 'SAVE_KEYWORDS') {
    handleSaveKeywords(msg.payload).then(sendResponse)
    return true
  }
  if (msg.type === 'SYNC_WORDBANK') {
    syncWordBank().then(sendResponse)
    return true
  }
  if (msg.type === 'OPEN_GAME') {
    chrome.tabs.create({ url: chrome.runtime.getURL('game.html') }).then(() => sendResponse({ ok: true }))
    return true
  }
  return false
})

chrome.action.onClicked.addListener(() => {
  chrome.tabs.create({ url: chrome.runtime.getURL('game.html') })
})

// Backstop reconciliation: EXPLAIN/SAVE_KEYWORDS trigger an immediate sync, but that alone
// misses drift from other devices/tabs or a silently-failed triggerSync(). MV3 service workers
// are ephemeral, so a periodic backstop needs chrome.alarms rather than setInterval.
chrome.alarms.create(WORDBANK_SYNC_ALARM, { periodInMinutes: WORDBANK_SYNC_PERIOD_MINUTES })

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === WORDBANK_SYNC_ALARM) {
    triggerSync()
  }
})
