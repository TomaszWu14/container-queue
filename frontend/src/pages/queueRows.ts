// Czyste helpery kolejki wyniesione z QueuePage.tsx (grupowanie dni, etykiety, klasy
// wierszy) — bez stanu Reacta, testowalne osobno. QueuePage je importuje.
import { localeFor } from '../i18n'
import { isoWeek, isoWeekYear, weekRange } from '../dates'
import type { Container } from '../types'

export interface DayRow { day: string; items: Container[] }

// Super-grupowanie dni po tygodniu ISO — lewa szyna „TYDZ." makiety scala pionowo
// swoje dni (rowspan). Dni bez daty trafiają do osobnego bloku bez tygodnia.
export interface WeekGroup {
  key: string            // `${rokISO}-W${tydzień}` albo 'none' dla dni bez daty
  week: number | null    // numer tygodnia ISO (null = brak daty)
  start: string          // poniedziałek tygodnia (ISO)
  end: string            // niedziela tygodnia (ISO)
  total: number          // suma kontenerów w tygodniu
  days: DayRow[]
}

export function groupByWeek(rows: DayRow[]): WeekGroup[] {
  const out: WeekGroup[] = []
  const byKey = new Map<string, WeekGroup>()
  for (const row of rows) {
    if (!row.day) {
      // dzień bez daty renderujemy poza tygodniem — nie doklejamy go do żadnego tygodnia
      out.push({ key: 'none', week: null, start: '', end: '', total: row.items.length, days: [row] })
      continue
    }
    const key = `${isoWeekYear(row.day)}-W${isoWeek(row.day)}`
    let g = byKey.get(key)
    if (!g) {
      const [start, end] = weekRange(row.day)
      g = { key, week: isoWeek(row.day), start, end, total: 0, days: [] }
      byKey.set(key, g)
      out.push(g)
    }
    g.days.push(row)
    g.total += row.items.length
  }
  return out
}

export function formatDayHeader(iso: string, lang: string) {
  const date = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(date.getTime())) return { weekday: '', full: iso }
  const locale = localeFor(lang)
  return {
    weekday: new Intl.DateTimeFormat(locale, { weekday: 'long' }).format(date),
    full: new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', year: 'numeric' }).format(date),
  }
}

export function groupByDay(containers: Container[]) {
  const groups = new Map<string, Container[]>()
  for (const c of containers) {
    const key = c.notify_date ?? ''
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(c)
  }
  return [...groups.entries()].sort(([a], [b]) => (a || '9999').localeCompare(b || '9999'))
}

// Ciągły zakres dni jak w kalendarzu — również puste, weekendy i święta.
export function buildDayRows(containers: Container[], dateFrom: string, dateTo: string, calendar: boolean): DayRow[] {
  const grouped = groupByDay(containers)
  const dated = grouped.filter(([day]) => day)
  const undated = grouped.filter(([day]) => !day)
  if (!calendar || dated.length === 0) {
    return grouped.map(([day, items]) => ({ day, items }))
  }
  const start = dateFrom || dated[0][0]
  const end = dateTo || dated[dated.length - 1][0]
  const byDay = new Map(dated)
  const rows: DayRow[] = []
  const included = new Set<string>()
  const cursor = new Date(`${start}T00:00:00Z`)
  const last = new Date(`${end}T00:00:00Z`)
  let guard = 0
  while (cursor <= last && guard++ < 400) {
    const iso = cursor.toISOString().slice(0, 10)
    rows.push({ day: iso, items: byDay.get(iso) ?? [] })
    included.add(iso)
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  for (const [day, items] of dated) {
    if (!included.has(day)) rows.push({ day, items })
  }
  return [...rows, ...undated.map(([day, items]) => ({ day, items }))]
}

// GRUPUJ WG Magazyn/Status — płaskie grupy zamiast dni. Czyste (etykiety i18n dokłada
// komponent po `key`). Magazyn: sort malejąco wg liczby; Status: kolejność cyklu życia
// (statusOrder), nieznane statusy na końcu w kolejności napotkania.
export function groupByKey(
  rows: DayRow[], mode: 'warehouse' | 'status',
  statusOrder: readonly string[], noWarehouse: string,
): { key: string; items: Container[] }[] {
  const m = new Map<string, Container[]>()
  const keyOf = mode === 'warehouse'
    ? (c: Container) => c.warehouse_name || noWarehouse
    : (c: Container) => c.status || '—'
  for (const r of rows) for (const c of r.items) {
    const k = keyOf(c)
    if (!m.has(k)) m.set(k, [])
    m.get(k)!.push(c)
  }
  let keys = [...m.keys()]
  if (mode === 'warehouse') keys.sort((a, b) => m.get(b)!.length - m.get(a)!.length)
  else keys = statusOrder.filter(s => m.has(s)).concat(keys.filter(k => !statusOrder.includes(k)))
  return keys.map(k => ({ key: k, items: m.get(k)! }))
}

export type PlanningStatus = 'POTWIERDZONE' | 'WYSLANE' | 'PROPOZYCJA'
export interface PlanningGroup { status: PlanningStatus; items: Container[] }

// kolejność sekcji w dniu: najpierw pewne, na końcu zgadywanki
const PLANNING_ORDER: PlanningStatus[] = ['POTWIERDZONE', 'WYSLANE', 'PROPOZYCJA']

export function splitByPlanning(items: Container[]): PlanningGroup[] {
  // ostatnia sekcja łapie też nieznany/brakujący status — kontener nie może zniknąć z dnia
  const known = new Set<string>(PLANNING_ORDER.slice(0, -1))
  return PLANNING_ORDER
    .map((status, i) => ({
      status,
      items: items.filter(c => (i === PLANNING_ORDER.length - 1
        ? !known.has(c.planning_status)
        : c.planning_status === status)),
    }))
    .filter(group => group.items.length > 0)   // puste sekcje nie zaśmiecają dnia
}

// różnicę liczymy tu, a nie w API — backend ma tę regułę w planning.eta_shift_days
export function etaShiftDays(c: Container): number | null {
  if (!c.planning_eta_at_send || !c.eta) return null
  const day = 24 * 60 * 60 * 1000
  return Math.round((Date.parse(c.eta) - Date.parse(c.planning_eta_at_send)) / day)
}
