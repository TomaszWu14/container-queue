// W11: czysta logika zegara przedawnienia + eksport CSV statystyk (testowalne bez DOM).
import type { ComplaintStats } from '../types'
import { csvCell } from '../api'

export type DeadlineTone = 'ok' | 'warn' | 'over'

// Zegar przedawnienia: kolor wg dni pozostałych (alertDays z konfiguracji backendu = 3).
export function deadlineTone(daysLeft: number | null, alertDays = 3): DeadlineTone | null {
  if (daysLeft === null || daysLeft === undefined) return null
  if (daysLeft < 0) return 'over'
  if (daysLeft <= alertDays) return 'warn'
  return 'ok'
}

// CSV rejestru szkód: sekcje dostawcy/armatorzy/koszty w jednym pliku (separator ;)
export function statsToCsv(stats: ComplaintStats, labels: {
  supplier: string; carrier: string; containers: string
  withComplaint: string; pct: string; currency: string
  claim: string; recovered: string; recoveryPct: string
}): string {
  const lines: string[] = []
  const section = (head: string[], rows: (string | number)[][]) => {
    lines.push(head.map(csvCell).join(';'))
    for (const row of rows) lines.push(row.map(csvCell).join(';'))
    lines.push('')
  }
  section([labels.supplier, labels.containers, labels.withComplaint, labels.pct],
    stats.suppliers.map(r => [r.name, r.containers, r.with_complaint, r.pct]))
  section([labels.carrier, labels.containers, labels.withComplaint, labels.pct],
    stats.carriers.map(r => [r.name, r.containers, r.with_complaint, r.pct]))
  section([labels.currency, labels.claim, labels.recovered, labels.recoveryPct],
    stats.costs.map(r => [r.currency, r.claim, r.recovered, r.recovery_pct]))
  return lines.join('\n')
}
