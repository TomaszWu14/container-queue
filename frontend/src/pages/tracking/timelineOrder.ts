// „Droga kontenera" wg etapów procesu, nie wg chwili zapisu (decyzja 2026-09-24).
// Nasze statusy mają datę KLIKNIĘCIA, zdarzenia wysyłki — datę zdarzenia; sortowane razem
// chronologicznie dawały np. „Awizowany 24.09" przed „ETA 11.10". Etap ustala kolejność,
// data porządkuje tylko wewnątrz etapu. Cofnięcia statusu zostają w historii obok.
import type { TimelineEntry } from './ContainerTimeline'

const STATUS_STAGE: Record<string, number> = {
  ZAPOWIEDZIANY: 10, W_PRODUKCJI: 12, TRANSPORT_WSTEPNY: 15, W_TRANSPORCIE: 20, W_PORCIE: 30, ODPRAWA: 40,
  AWIZOWANY: 50, W_DOSTAWIE: 60, DOSTARCZONY: 70, ZREALIZOWANY: 80,
}
// DEMURRAGE w etapie awizacji: termin porównywany z datą awizacji (po dacie widać, czy zdąży)
const PLANNED_STAGE: Record<string, number> = { ETD: 20, ETA: 30, NOTIFY: 50, DEMURRAGE: 50, ATD: 60 }

export function stageOf(e: TimelineEntry): number {
  if (e.kind === 'system') return STATUS_STAGE[e.code.replace(/^STATUS_/, '')] ?? 90
  if (e.kind === 'order') return 10
  if (e.kind === 'carrier' || e.kind === 'vessel') return 20
  return PLANNED_STAGE[e.code] ?? 90
}

// wejście: wpisy z backendu w kolejności chronologicznej
export function orderByStage(entries: TimelineEntry[]): TimelineEntry[] {
  const statuses = entries.filter(e => e.kind === 'system')
  const current = statuses.length ? stageOf(statuses[statuses.length - 1]) : Infinity
  const latest = new Map(statuses.map(e => [e.code, e]))   // ostatni wpis danego statusu
  const kept = entries.filter(e => e.kind !== 'system' || (latest.get(e.code) === e && stageOf(e) <= current))
  const at = (e: TimelineEntry) => (e.at ? e.at : '￿')   // brak daty na koniec etapu
  return kept.map((e, i) => ({ e, i }))
    .sort((a, b) => stageOf(a.e) - stageOf(b.e) || at(a.e).localeCompare(at(b.e)) || a.i - b.i)
    .map(x => x.e)
}
