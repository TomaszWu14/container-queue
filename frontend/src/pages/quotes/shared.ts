import { useState } from 'react'
import { formatNum } from '../../dates'
import type { Quote, TransportJob } from '../../types'

// Wspólne stałe i typy paneli spedycji (wyceny) — wydzielone z QuotesPage.tsx.
export const JOB_CLASS: Record<string, string> = {
  SZKIC: 'st-ZAPOWIEDZIANY', WYSLANE: 'st-W_TRANSPORCIE',
  ZLECONE: 'st-ZREALIZOWANY', ANULOWANE: 'cs-REWIZJA',
}
export const QUOTE_CLASS: Record<string, string> = {
  ZAPYTANIE: 'st-ZAPOWIEDZIANY', WYCENIONA: 'st-W_TRANSPORCIE',
  WYBRANA: 'st-ZREALIZOWANY', ODRZUCONA: 'cs-REWIZJA', WYGASLA: 'cs-REWIZJA',
}
export const money = (q: Quote) => q.amount != null ? `${formatNum(q.amount)} ${q.currency}` : '—'

export type OnAction = (fn: () => Promise<TransportJob>) => void

export interface CostRow { month: string; currency: string; total: number; count: number }
export interface PerfRow {
  forwarder_id: number; forwarder: string; invited: number; responded: number
  won: number; no_equipment: number; rolls: number
  response_rate: number; win_rate: number; avg_transit: number | null
}

// Mini-hook: jeden wzorzec busy+submit zamiast kopii useState(busy) w każdym formularzu.
// Obsługę błędów robi onAction (rodzic) — hook pilnuje tylko blokady podwójnego submitu.
export function useSubmit() {
  const [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<unknown> | void) => {
    if (busy) return
    setBusy(true)
    try { await fn() } finally { setBusy(false) }
  }
  return { busy, run }
}
