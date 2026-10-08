// Strażnik sum narastających (2026-09-24): wt 3 + śr 3 → w środę Σ 6, z podziałem na magazyny.
import { describe, expect, it } from 'vitest'
import { cumulativeByDay } from './queueSummary'
import type { Container } from '../types'

const c = (warehouse_name: string | null) => ({ warehouse_name }) as Container

describe('cumulativeByDay', () => {
  it('sumuje dni tygodnia po kolei, osobno per magazyn', () => {
    const cum = cumulativeByDay([
      { day: '2026-09-29', items: [c('DLT'), c('DLT'), c('ACME')] },
      { day: '2026-09-30', items: [c('DLT'), c('ACME'), c(null)] },
      { day: '2026-10-01', items: [] },
    ])
    expect(cum.get('2026-09-29')!.total).toBe(3)
    expect(cum.get('2026-09-30')).toEqual({ total: 6, byWh: { DLT: 3, ACME: 2, '—': 1 } })
    expect(cum.get('2026-10-01')!.total).toBe(6)   // pusty dzień nie zeruje sumy
  })
})
