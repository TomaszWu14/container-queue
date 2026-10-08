// Kalendarz awizacji (makieta Claude Design „Kalendarz awizacji", 2026-09-24): wyliczenia
// dnia / tygodnia / miesiąca z danych /api/queue — bez nowego API. Czyste funkcje (test).
import type { Container, QueueDay } from '../../types'

export type WhStat = { key: string; n: number; limit: number }
export type DayStat = {
  total: number; cap: number; free: number; over: number; late: number
  customsOpen: number; revision: number; vessels: number; toPort: number
  byWh: WhStat[]; closed: boolean
}

const DONE_CUSTOMS = new Set(['ODPRAWIONY', 'ZWOLNIONY', 'ROZLICZONY'])
export const whName = (c: Container) => (c.warehouse_name || '').toUpperCase()

// ETA w porcie: statki i kontenery przypływające danego dnia (z całego pobranego zakresu)
export function etaIndex(days: QueueDay[]): Map<string, Container[]> {
  const out = new Map<string, Container[]>()
  for (const d of days) for (const c of d.containers) {
    if (!c.eta) continue
    const k = c.eta.slice(0, 10)
    out.set(k, [...(out.get(k) ?? []), c])
  }
  return out
}

export function dayStat(info: QueueDay | undefined, whs: { key: string; limit: number }[],
                        eta: Container[] = [], filter = ''): DayStat {
  const all = info?.containers ?? []
  const items = filter ? all.filter(c => whName(c) === filter) : all
  const shown = filter ? whs.filter(w => w.key === filter) : whs
  const byWh = shown.map(w => ({ key: w.key, limit: w.limit, n: items.filter(c => whName(c) === w.key).length }))
  const cap = byWh.reduce((s, w) => s + w.limit, 0)
  const free = byWh.reduce((s, w) => s + Math.max(0, w.limit - w.n), 0)
  const over = byWh.reduce((s, w) => s + Math.max(0, w.n - w.limit), 0)
  return {
    total: items.length, cap, free, over,
    late: items.filter(c => c.is_delayed).length,
    customsOpen: items.filter(c => !DONE_CUSTOMS.has(c.customs_status)).length,
    revision: items.filter(c => c.customs_status === 'REWIZJA').length,
    vessels: new Set(eta.map(c => c.vessel).filter(Boolean)).size,
    toPort: eta.length,
    byWh, closed: !!info?.is_free_day,
  }
}

// obłożenie → kolor pierścienia/progu (spójnie: niski / wysoki / ponad limit)
export function tone(total: number, cap: number): 'low' | 'high' | 'over' | 'none' {
  if (!total) return 'none'
  if (!cap) return 'high'
  if (total > cap) return 'over'
  return total / cap >= 0.7 ? 'high' : 'low'
}

export type Totals = { bookings: number; cap: number; free: number; late: number; overDays: number
  workdays: number; customsOpen: number; calls: number }

export function totals(stats: DayStat[]): Totals {
  const open = stats.filter(s => !s.closed)
  return {
    bookings: open.reduce((s, d) => s + d.total, 0),
    cap: open.reduce((s, d) => s + d.cap, 0),
    free: open.reduce((s, d) => s + d.free, 0),
    late: stats.reduce((s, d) => s + d.late, 0),
    overDays: open.filter(d => d.over > 0).length,
    workdays: open.length,
    customsOpen: stats.reduce((s, d) => s + d.customsOpen, 0),
    calls: stats.reduce((s, d) => s + d.vessels, 0),
  }
}

export const pct = (n: number, cap: number) => (cap ? Math.round((n / cap) * 100) : 0)

// siatka miesiąca: tygodnie (pon–nd) z ISO dni albo null poza miesiącem
export function monthWeeks(year: number, month: number): (string | null)[][] {
  const first = new Date(Date.UTC(year, month, 1))
  const days = new Date(Date.UTC(year, month + 1, 0)).getUTCDate()
  const cells: (string | null)[] = Array((first.getUTCDay() + 6) % 7).fill(null)
  for (let d = 1; d <= days; d++) cells.push(new Date(Date.UTC(year, month, d)).toISOString().slice(0, 10))
  while (cells.length % 7) cells.push(null)
  return Array.from({ length: cells.length / 7 }, (_, i) => cells.slice(i * 7, i * 7 + 7))
}
