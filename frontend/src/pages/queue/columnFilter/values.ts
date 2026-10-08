// Filtry kolumn „jak w Excelu" — czysta logika (bez Reacta): klucze wartości komórki per kolumna,
// stan w URL (?kolumny=<JSON>), filtrowanie wierszy, lista unikalnych wartości z licznikami i chipy.
// Klucz = surowa, stabilna wartość (data ISO, kod statusu) — URL nie zależy od języka;
// etykieta = tekst jak w komórce (sformatowana data, nazwa statusu).
import { formatDate } from '../../../dates'
import type { Container } from '../../../types'
import { NO_WAREHOUSE, splitMulti, warehouseKey } from '../../queueSummary'
import { idLabel } from '../cells'
import { COLUMN_LABEL } from '../columns'
import { demurrageDaysLeft, demurrageLabel, stageName } from '../enterprise'

type T = (k: string) => string
type Kind = 'text' | 'date' | 'num'
interface Spec { keys: (c: Container, today: string) => string[]; kind?: Kind; label?: (k: string, t: T) => string }

const one = (v: string | null | undefined) => (v ? [v] : [])
const day = (v: string | null | undefined) => (v ? [v.slice(0, 10)] : [])
const dateLabel = (k: string) => formatDate(k)

/** Kolumny z filtrem (bez „Wypełn." — % liczony asynchronicznie tylko dla widocznych wierszy). */
export const FILTER_COLS: Record<string, Spec> = {
  no: { keys: c => one(idLabel(c) === '—' ? '' : idLabel(c)) },
  company: { keys: c => one(c.company_name) },
  supplier: { keys: c => one(c.supplier_name) },
  vessel: { keys: c => one(c.vessel) },
  eta: { keys: c => day(c.atd ?? c.eta ?? c.eta_estimate), kind: 'date', label: dateLabel },
  notify: { keys: c => day(c.notify_date), kind: 'date', label: dateLabel },
  status: { keys: c => one(c.status), label: (k, t) => stageName(t(`st_${k}`)) },
  customs: { keys: c => one(c.customs_status === 'BRAK' ? '' : c.customs_status), label: (k, t) => t(`cs_${k}`) },
  wh: { keys: c => one(warehouseKey(c.warehouse_name) === NO_WAREHOUSE ? '' : c.warehouse_name) },
  fwd: { keys: c => one(c.forwarder_name) },
  order: { keys: c => splitMulti(c.order_numbers || c.order_number) },
  dem: {
    keys: (c, today) => { const left = demurrageDaysLeft(c, today); return left === null ? [] : [String(left)] },
    kind: 'num', label: (k, t) => demurrageLabel(Number(k), t('kqDaysLeft')),
  },
  etd: { keys: c => day(c.etd), kind: 'date', label: dateLabel },
  transport: { keys: c => one(c.transport_type), label: (k, t) => t(`transport_${k}`) },
  onCarriage: { keys: c => one(c.on_carriage), label: (k, t) => t(`transport_${k}`) },
  deliveryNote: { keys: c => one(c.delivery_note) },
  incomingNo: { keys: c => splitMulti(c.incoming_delivery_no) },
  purchaseNote: { keys: c => one(c.purchase_note) },
  docFlow: { keys: c => one(c.document_flow) },
  sentReq: { keys: c => (c.sent_required == null ? [] : [c.sent_required ? 'yes' : 'no']), label: (k, t) => t(k) },
  sentNo: { keys: c => one(c.sent_number) },
  sentStatus: { keys: c => one(c.sent_status) },
}

/** Pusta komórka = klucz '' → „(Puste)". */
export const EMPTY = ''
const cellKeys = (col: string, c: Container, today: string) => {
  const keys = FILTER_COLS[col]?.keys(c, today) ?? []
  return keys.length ? keys : [EMPTY]
}

/** in = pokaż tylko te wartości; out = ukryj te wartości (zapisujemy krótszą listę — URL). */
export type ColFilter = { in: string[] } | { out: string[] }
export type ColFilters = Record<string, ColFilter>

// URL bywa ręcznie edytowany / stary — zły kształt = brak filtra, nie wyjątek
export function parseColFilters(raw: string): ColFilters {
  if (!raw) return {}
  try {
    const obj: unknown = JSON.parse(raw)
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return {}
    const out: ColFilters = {}
    for (const [col, v] of Object.entries(obj as Record<string, unknown>)) {
      if (!FILTER_COLS[col] || !v || typeof v !== 'object') continue
      const list = (v as { in?: unknown; out?: unknown }).in ?? (v as { out?: unknown }).out
      if (!Array.isArray(list)) continue
      const vals = list.filter((x): x is string => typeof x === 'string')
      out[col] = 'in' in (v as object) ? { in: vals } : { out: vals }
    }
    return out
  } catch { return {} }
}

export const serializeColFilters = (f: ColFilters) => (Object.keys(f).length ? JSON.stringify(f) : '')

export function withColFilter(f: ColFilters, col: string, next: ColFilter | null): ColFilters {
  const copy = { ...f }
  if (next) copy[col] = next; else delete copy[col]
  return copy
}

/** Wiersz przechodzi, gdy którakolwiek jego wartość (komórki wielowartościowe) jest wybrana. */
function passes(col: string, flt: ColFilter, c: Container, today: string): boolean {
  const keys = cellKeys(col, c, today)
  if ('in' in flt) { const s = new Set(flt.in); return keys.some(k => s.has(k)) }
  const s = new Set(flt.out)
  return keys.some(k => !s.has(k))
}

/** Filtry kolumn łączone AND; `except` = pomiń tę kolumnę (kaskada listy wartości jak w Excelu). */
export function applyColFilters(rows: Container[], f: ColFilters, today: string, except?: string): Container[] {
  const active = Object.entries(f).filter(([col]) => col !== except)
  if (active.length === 0) return rows
  return rows.filter(c => active.every(([col, flt]) => passes(col, flt, c, today)))
}

export type ValueOpt = { key: string; label: string; count: number }

/** Unikalne wartości kolumny z licznikami wierszy; daty chronologicznie, liczby rosnąco,
 *  tekst alfabetycznie (pl); „(Puste)" na końcu. */
export function columnValues(col: string, rows: Container[], today: string, t: T): ValueOpt[] {
  const spec = FILTER_COLS[col]
  if (!spec) return []
  const counts = new Map<string, number>()
  for (const c of rows) for (const k of new Set(cellKeys(col, c, today))) counts.set(k, (counts.get(k) ?? 0) + 1)
  const label = (k: string) => (k === EMPTY ? '' : spec.label ? spec.label(k, t) : k)
  const opts = [...counts].map(([key, count]) => ({ key, label: label(key), count }))
  const cmp = spec.kind === 'num' ? (a: ValueOpt, b: ValueOpt) => Number(a.key) - Number(b.key)
    : spec.kind === 'date' ? (a: ValueOpt, b: ValueOpt) => a.key.localeCompare(b.key)
      : (a: ValueOpt, b: ValueOpt) => a.label.localeCompare(b.label, 'pl', { numeric: true, sensitivity: 'base' })
  return opts.sort((a, b) => (a.key === EMPTY ? 1 : b.key === EMPTY ? -1 : cmp(a, b)))
}

/** Stan listy przy otwarciu: bez filtra wszystko zaznaczone. */
export function initialChecked(flt: ColFilter | undefined, opts: ValueOpt[]): Set<string> {
  const keys = opts.map(o => o.key)
  if (!flt) return new Set(keys)
  if ('in' in flt) { const s = new Set(flt.in); return new Set(keys.filter(k => s.has(k))) }
  const s = new Set(flt.out)
  return new Set(keys.filter(k => !s.has(k)))
}

/** Zaznaczenie → filtr: wszystko = brak filtra; inaczej krótsza z list in/out. */
export function toFilter(checked: Set<string>, opts: ValueOpt[]): ColFilter | null {
  const keys = opts.map(o => o.key)
  const inList = keys.filter(k => checked.has(k))
  if (inList.length === keys.length) return null
  const outList = keys.filter(k => !checked.has(k))
  return outList.length < inList.length ? { out: outList } : { in: inList }
}

export const colLabel = (col: string, t: T) => t(COLUMN_LABEL[col] ?? col)

/** Chipy w istniejącym pasku filtrów (decyzja 15): „Statek: MV DEMO DELTA, COSCO". */
export function colFilterChips(f: ColFilters, t: T, set: (col: string, v: ColFilter | null) => void) {
  return Object.entries(f).map(([col, flt]) => {
    const spec = FILTER_COLS[col]
    const name = (k: string) => (k === EMPTY ? t('cfEmpty') : spec.label ? spec.label(k, t) : k)
    const list = ('in' in flt ? flt.in : flt.out).map(name)
    const shown = list.slice(0, 3).join(', ') + (list.length > 3 ? ` +${list.length - 3}` : '')
    return {
      key: `kol-${col}`,
      label: `${colLabel(col, t)}: ${'in' in flt ? shown : `${t('cfExcept')} ${shown}`}`,
      onClear: () => set(col, null),
    }
  })
}
