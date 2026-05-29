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

export type MeaningItem = {
  vi: string
  description: string
}

export type MeaningGroup = {
  pos: string
  items: MeaningItem[]
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
  query_count?: number
  cached: boolean
  db_hit?: boolean
  audio_url?: string | null
  vdict_examples?: Array<{ en: string; vi: string }>
  meanings?: MeaningGroup[] | null
}

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
  | { type: 'SYNC_WORDBANK' }
  | { type: 'OPEN_GAME' }

export type ExplainResult = { ok: true; data: ExplainResponse } | { ok: false; error: string }
export type SaveResult = { ok: true } | { ok: false; error: string }

export interface PracticeItem {
  id: string
  text: string
  word_type?: string | null
  pronunciation?: string | null
  explanation: string
  example?: string | null
  synonyms: string[]
  collocations: string[]
  difficulty?: string | null
  audio_url?: string | null
  vdict_examples?: Array<{ en: string; vi: string }>
  added_at: string
  next_review: string
  interval: number
  ease: number
  review_count: number
  last_level?: 'strong' | 'medium' | 'low' | null
}

export interface WordBankOptions {
  retentionDays: number
  dateFilter: 'today' | 'week' | 'month' | 'all'
}

export const DEFAULT_BACKEND_URL = 'http://localhost:8000'
export const WORDBANK_STORAGE_KEY = 'wordBank'
export const WORDBANK_SYNCED_AT_KEY = 'wordBankSyncedAt'
export const POPUP_THEME_KEY = 'popupTheme'
export const PRACTICE_LIST_KEY = 'practiceList'
export const WORDBANK_OPTIONS_KEY = 'wordBankOptions'
