import { describe, expect, it } from 'vitest'
import { etaShiftDays, splitByPlanning } from './pages/queueRows'
import type { Container } from './types'

const make = (id: number, planning_status: string, extra: Partial<Container> = {}) =>
  ({ id, container_no: `C${id}`, planning_status, ...extra } as unknown as Container)

describe('splitByPlanning', () => {
  it('zwraca sekcje w kolejności: potwierdzone, wysłane, propozycje', () => {
    const groups = splitByPlanning([
      make(1, 'PROPOZYCJA'), make(2, 'POTWIERDZONE'), make(3, 'WYSLANE'),
    ])
    expect(groups.map(g => g.status)).toEqual(['POTWIERDZONE', 'WYSLANE', 'PROPOZYCJA'])
    expect(groups[0].items.map(c => c.id)).toEqual([2])
  })

  it('pomija puste sekcje', () => {
    const groups = splitByPlanning([make(1, 'PROPOZYCJA')])
    expect(groups.map(g => g.status)).toEqual(['PROPOZYCJA'])
  })
})

describe('etaShiftDays', () => {
  it('liczy przesunięcie ETA od zamrożenia planu', () => {
    expect(etaShiftDays(make(1, 'WYSLANE', {
      eta: '2026-10-08', planning_eta_at_send: '2026-10-01' } as Partial<Container>))).toBe(7)
  })

  it('bez zdjęcia ETA nie ma czego porównać', () => {
    expect(etaShiftDays(make(1, 'WYSLANE', { eta: '2026-10-08' } as Partial<Container>))).toBeNull()
  })
})

describe('splitByPlanning — odporność', () => {
  it('kontener bez statusu planowania nie znika, ląduje w propozycjach', () => {
    const groups = splitByPlanning([make(1, undefined as unknown as string)])
    expect(groups.map(g => g.status)).toEqual(['PROPOZYCJA'])
    expect(groups[0].items.map(c => c.id)).toEqual([1])
  })
})
