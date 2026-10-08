import { describe, expect, it } from 'vitest'
import { deadlineTone, statsToCsv } from './complaintUtils'

describe('deadlineTone (zegar przedawnienia)', () => {
  it('null gdy brak terminu', () => expect(deadlineTone(null)).toBeNull())
  it('ok gdy daleko', () => expect(deadlineTone(14)).toBe('ok'))
  it('warn w oknie alertu (<= 3 dni)', () => {
    expect(deadlineTone(3)).toBe('warn')
    expect(deadlineTone(0)).toBe('warn')
  })
  it('over po terminie', () => expect(deadlineTone(-1)).toBe('over'))
  it('respektuje inny próg alertu', () => expect(deadlineTone(5, 7)).toBe('warn'))
})

describe('statsToCsv', () => {
  const labels = {
    supplier: 'Dostawca', carrier: 'Armator', containers: 'Kontenery',
    withComplaint: 'Z reklamacją', pct: '%', currency: 'Waluta',
    claim: 'Roszczenia', recovered: 'Odzyskano', recoveryPct: '% odzysku',
  }
  it('składa trzy sekcje i escapuje średniki', () => {
    const csv = statsToCsv({
      months: 12,
      suppliers: [{ name: 'Firma; A', containers: 4, with_complaint: 1, pct: 25 }],
      carriers: [{ name: 'Maersk', containers: 4, with_complaint: 2, pct: 50 }],
      costs: [{ currency: 'USD', claim: 1000, recovered: 250, recovery_pct: 25 }],
    }, labels)
    expect(csv).toContain('Dostawca;Kontenery;Z reklamacją;%')
    expect(csv).toContain('"Firma; A";4;1;25')
    expect(csv).toContain('Maersk;4;2;50')
    expect(csv).toContain('USD;1000;250;25')
  })
})
