// Czyste helpery widoku tygodniowego kolejki (projekt „Kolejka - palety" 4a):
// podsumowanie zakresu, rozbicie per magazyn, wysokość wiersza i rozwijanie
// wielowartościowych komórek (PO / SENT). Bez stanu Reacta — testowalne osobno.
import type { Container } from '../types'
import type { DayRow } from './queueRows'

/* ---- magazyny ------------------------------------------------------------ */

// Magazyn bez przypisania dostaje własny klucz — inaczej kontener wypadłby
// z sumy i kafle nie zgadzałyby się z licznikiem dnia.
export const NO_WAREHOUSE = '—'

// Nazwa magazynu bywa zapisana jako „DLT Radom" czy „ACME DLT", więc dopasowujemy
// po słowie (jak kolor magazynu w kolejce). DLT sprawdzamy pierwszy: „ACME DLT" to DLT.
const KNOWN_WAREHOUSES = ['DLT', 'ACME', 'BOREALIS', 'COBALTSPORT', 'IBERIA']

export function warehouseKey(name: string | null): string {
  const raw = (name ?? '').trim()
  if (raw === '') return NO_WAREHOUSE
  const upper = raw.toUpperCase()
  const words = upper.split(/[^A-Z0-9]+/).filter(Boolean)
  for (const known of KNOWN_WAREHOUSES) {
    if (words.includes(known)) return known
  }
  // Nieznany magazyn zachowuje własną nazwę — podziału na słowa użyć tu nie można,
  // bo klasa [A-Z0-9] gubi polskie znaki („Nowy Skład" → „NOWY SK AD").
  return upper
}

// klasa CSS kafla/pigułki magazynu — kolor tylko dla znanych magazynów, reszta neutralna
export function warehouseClass(key: string): string {
  return KNOWN_WAREHOUSES.includes(key) ? `wh-${key.toLowerCase()}` : 'wh-other'
}

export function countByWarehouse(items: Container[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const c of items) {
    const key = warehouseKey(c.warehouse_name)
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return counts
}

export interface WarehouseStat {
  key: string
  n: number
  /** udział w sumie zakresu, 0–100 (zaokrąglony) — podpis i szerokość paska */
  pct: number
}

/* ---- podsumowanie zakresu ------------------------------------------------ */

export interface RangeSummary {
  total: number
  /** dni z co najmniej jedną dostawą */
  activeDays: number
  /** wszystkie dni w zakresie (także puste) */
  totalDays: number
  late: number
  /** magazyny obecne w zakresie, malejąco po liczbie kontenerów */
  warehouses: WarehouseStat[]
}

export function summarizeRange(rows: DayRow[]): RangeSummary {
  const items = rows.flatMap(row => row.items)
  const counts = countByWarehouse(items)
  const total = items.length
  return {
    total,
    activeDays: rows.filter(row => row.items.length > 0).length,
    totalDays: rows.length,
    late: items.filter(c => c.is_delayed).length,
    warehouses: [...counts.entries()]
      // stabilna kolejność: malejąco po liczbie, przy remisie alfabetycznie
      .sort(([ka, na], [kb, nb]) => nb - na || ka.localeCompare(kb))
      .map(([key, n]) => ({ key, n, pct: total > 0 ? Math.round((n / total) * 100) : 0 })),
  }
}

/** Pigułki magazynów na pasmie dnia: zestaw z całego zakresu, 0 = wyblakła. */
// Sumy narastające dni tygodnia (2026-09-24): wt 3 + śr 3 → w środę Σ 6. Liczone w obrębie
// jednego bloku (tygodnia), z podziałem na magazyny — wejście: dni w kolejności kalendarza.
export type Cumulative = { total: number; byWh: Record<string, number> }
export function cumulativeByDay(days: { day: string; items: Container[] }[]): Map<string, Cumulative> {
  const out = new Map<string, Cumulative>()
  let total = 0
  const byWh: Record<string, number> = {}
  for (const d of days) {
    total += d.items.length
    for (const [key, n] of countByWarehouse(d.items)) byWh[key] = (byWh[key] ?? 0) + n
    out.set(d.day, { total, byWh: { ...byWh } })
  }
  return out
}

export function bandWarehouses(items: Container[], keys: string[]): WarehouseStat[] {
  const counts = countByWarehouse(items)
  return keys.map(key => ({ key, n: counts.get(key) ?? 0, pct: 0 }))
}

/* ---- komórki wielowartościowe (PO / SENT) -------------------------------- */

// Backend trzyma numery w jednym polu tekstowym (nowa linia / przecinek / średnik
// zależnie od importu) — rozbijamy je tu, żeby dało się je zwinąć do „+N".
// `_x000D_` to Excelowy escape znaku CR z importu xlsx — traktujemy jak separator,
// żeby nie wyciekał do UI ani nie robił wielolinijkowych, wysokich wierszy.
export function splitMulti(raw: string | null): string[] {
  return (raw ?? '').split(/(?:_x000D_|[\r\n,;])+/).map(s => s.trim()).filter(Boolean)
}

// czyszczenie surowego tekstu wielolinijkowego (notatki) z Excelowych `_x000D_` → realny \n
export function cleanMultiline(raw: string | null): string {
  return (raw ?? '').replace(/_x000D_/g, '\n').replace(/\r/g, '')
}
