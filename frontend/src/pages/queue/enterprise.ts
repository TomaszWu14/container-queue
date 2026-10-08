// Kolejka Enterprise — czysta logika: zakładki widoków (z licznikami), grupowanie.
// Bez Reacta — testowane w enterprise.test.ts.
import type { Container } from '../../types'
import { CONTAINER_STATUSES } from '../../types'
import { groupByDay, groupByKey, splitByPlanning } from '../queueRows'
import { NO_WAREHOUSE } from '../queueSummary'
import type { GroupBy } from './config'
import type { DocTilesMap } from './docTiles'

export type QueueView = 'all' | 'late' | 'demurrage' | 'customs' | 'mine' | 'docsMissing' | 'intake'
export const QUEUE_VIEWS: QueueView[] = ['all', 'late', 'demurrage', 'customs', 'mine', 'docsMissing', 'intake']
// grupowanie = preferencja GroupBy z useViewPrefs: weekday = Dzień, status = Etap
export const GROUP_MODES: GroupBy[] = ['weekday', 'status', 'warehouse']

/** Próg zakładki/KPI „Demurrage ≤ 2 dni". */
export const DEMURRAGE_SOON_DAYS = 2

// Odprawa „otwarta" = rozpoczęta (dokumenty / zlecona / draft / rewizja), jeszcze nieodprawiona
const CUSTOMS_OPEN = new Set(['DOKUMENTY_KOMPLETNE', 'ZLECONA', 'DRAFT_WYSLANY', 'DRAFT_POTWIERDZONY', 'REWIZJA'])

const dayMs = 86_400_000
/** Dni do terminu demurrage (ujemne = po terminie); null, gdy backend terminu nie policzył. */
export function demurrageDaysLeft(c: Container, today: string): number | null {
  if (!c.demurrage_deadline) return null
  return Math.round((Date.parse(c.demurrage_deadline) - Date.parse(today)) / dayMs)
}

/** Etykieta demurrage: po terminie „+N d", dziś „0 d", przed terminem wg wzorca („{n} d"). */
export function demurrageLabel(left: number, pattern: string): string {
  return left < 0 ? `+${-left} d` : pattern.replace('{n}', String(left))
}

/** Nazwa etapu bez prefiksu numeru („4 · Transport morski" → „Transport morski"). */
export const stageName = (label: string) => label.replace(/^\d+\s*·\s*/, '')

/** „N zaznaczony / zaznaczone / zaznaczonych" (odmiana PL; EN/PT bez odmiany przez liczbę). */
export function selectedLabel(n: number, lang: string): string {
  if (lang === 'pl') {
    const m10 = n % 10, m100 = n % 100
    const word = n === 1 ? 'zaznaczony'
      : m10 >= 2 && m10 <= 4 && !(m100 >= 12 && m100 <= 14) ? 'zaznaczone' : 'zaznaczonych'
    return `${n} ${word}`
  }
  if (lang === 'pt') return `${n} ${n === 1 ? 'selecionado' : 'selecionados'}`
  return `${n} selected`
}

export const isDemurrageSoon = (c: Container, today: string) => {
  const left = demurrageDaysLeft(c, today)
  return left !== null && left <= DEMURRAGE_SOON_DAYS
}
export const isCustomsOpen = (c: Container) => CUSTOMS_OPEN.has(c.customs_status)

export function matchesView(c: Container, view: QueueView, today: string, watched: Set<number>,
  docs: DocTilesMap = {}) {
  switch (view) {
    // mini-kafelki dochodzą osobnym żądaniem — do ich nadejścia zakładki są puste
    case 'docsMissing': return (docs[c.id]?.missing.length ?? 0) > 0
    case 'intake': return (docs[c.id]?.intake_pending ?? 0) > 0
    case 'late': return c.is_delayed
    case 'demurrage': return isDemurrageSoon(c, today)
    case 'customs': return isCustomsOpen(c)
    case 'mine': return watched.has(c.id)
    default: return true
  }
}

/** Liczniki na zakładkach widoków (jedno przejście na widok — listy są małe). */
export function viewCounts(items: Container[], today: string, watched: Set<number>, docs: DocTilesMap = {}) {
  return Object.fromEntries(QUEUE_VIEWS.map(v =>
    [v, items.filter(c => matchesView(c, v, today, watched, docs)).length])) as Record<QueueView, number>
}

export interface RowGroup { key: string; items: Container[] }

/** Kolejność wierszy na ekranie (grupy → sekcje planowania → sort) — nawigacja ‹ › szuflady. */
export function rowOrder(groups: RowGroup[], sortItems: (items: Container[]) => Container[]): number[] {
  return groups.flatMap(g => splitByPlanning(g.items).flatMap(p => sortItems(p.items).map(c => c.id)))
}
// Dzień: rosnąco po dacie awizacji, bez daty na końcu (key ''); Etap: cykl życia statusu;
// Magazyn: malejąco wg liczby (bez magazynu = NO_WAREHOUSE).
export function groupContainers(items: Container[], mode: GroupBy): RowGroup[] {
  if (mode === 'weekday') return groupByDay(items).map(([key, group]) => ({ key, items: group }))
  return groupByKey([{ day: '', items }], mode,
    CONTAINER_STATUSES, NO_WAREHOUSE)
}
