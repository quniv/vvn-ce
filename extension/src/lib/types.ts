// Shared types between content script, service worker, popup, options, and game

export type KeywordItem = {
  text: string
  word_type?: string | null
  pronunciation?: string | null
  explanation: string
  example?: string | null
  synonyms?: string[]
  collocations?: string[]
  difficulty?: string | null
}

export type ExplainResponse = {
  kind: 'word' | 'sentence'
  text: string
  word_type?: string | null
  pronunciation?: string | null
  explanation: string
  example?: string | null
  synonyms?: string[]
  collocations?: string[]
  difficulty?: string | null
  keywords: KeywordItem[]
  saved: boolean
  saved_id?: string | null
  model_source?: string | null
  up_vote: number
  down_vote: number
  query_count?: number
  cached: boolean
  db_hit?: boolean
}

export type VoteDirection = 'up' | 'down'

export type WordRead = {
  id: string
  text: string
  word_type?: string | null
  pronunciation?: string | null
  explanation: string
  example?: string | null
  synonyms?: string[]
  collocations?: string[]
  difficulty?: string | null
  source_url?: string | null
  source_sentence?: string | null
  model_source?: string | null
  up_vote: number
  down_vote: number
  query_count: number
  last_queried_at: string
  created_at: string
}

export type WordBankResponse = { ok: true; data: WordRead[]; syncedAt: string } | { ok: false; error: string }

export type Message =
  | { type: 'EXPLAIN'; payload: { text: string; source_url?: string } }
  | {
      type: 'SAVE_KEYWORDS'
      payload: { source_sentence: string; source_url?: string; keywords: KeywordItem[] }
    }
  | { type: 'VOTE'; payload: { wordId: string; direction: VoteDirection } }
  | { type: 'SYNC_WORDBANK' }
  | { type: 'OPEN_GAME' }

export type ExplainResult = { ok: true; data: ExplainResponse } | { ok: false; error: string }
export type SaveResult = { ok: true } | { ok: false; error: string }
export type VoteResult = { ok: true; data: WordRead } | { ok: false; error: string }

export const DEFAULT_BACKEND_URL = 'http://localhost:8000'
export const WORDBANK_STORAGE_KEY = 'wordBank'
export const WORDBANK_SYNCED_AT_KEY = 'wordBankSyncedAt'
export const POPUP_THEME_KEY = 'popupTheme'
