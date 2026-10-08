import { describe, expect, it } from 'vitest'
import type { Container } from '../../types'
import {
  demurrageDaysLeft, demurrageLabel, groupContainers, rowOrder, selectedLabel, stageName, matchesView, viewCounts,
} from './enterprise'

const make = (id: number, extra: Partial<Container> = {}) => ({
  id, container_no: `C${id}`, is_delayed: false, customs_status: 'BRAK', status: 'W_TRANSPORCIE',
  notify_date: null, warehouse_name: null, demurrage_deadline: null, ...extra,
} as unknown as Container)

const TODAY = '2026-09-25'

describe('widoki kolejki', () => {
  const items = [
    make(1, { is_delayed: true }),
    make(2, { demurrage_deadline: '2026-09-27' }),   // za 2 dni → łapie się
    make(3, { demurrage_deadline: '2026-09-28' }),   // za 3 dni → nie
    make(4, { customs_status: 'ZLECONA' }),
    make(5, { customs_status: 'ODPRAWIONY' }),
  ]

  it('demurrage liczy dni do terminu (po terminie ujemne, brak terminu = null)', () => {
    expect(demurrageDaysLeft(items[1], TODAY)).toBe(2)
    expect(demurrageDaysLeft(make(9, { demurrage_deadline: '2026-09-20' }), TODAY)).toBe(-5)
    expect(demurrageDaysLeft(items[0], TODAY)).toBeNull()
  })

  it('zakładki: Moje = obserwowane, liczniki per widok', () => {
    const watched = new Set([3, 5])
    expect(items.filter(c => matchesView(c, 'mine', TODAY, watched)).map(c => c.id)).toEqual([3, 5])
    expect(viewCounts(items, TODAY, watched))
      .toEqual({ all: 5, late: 1, demurrage: 1, customs: 1, mine: 2, docsMissing: 0, intake: 0 })
  })
})

describe('groupContainers', () => {
  const items = [
    make(1, { notify_date: '2026-09-26', status: 'AWIZOWANY', warehouse_name: 'DLT' }),
    make(2, { notify_date: null, status: 'W_PORCIE', warehouse_name: 'ACME' }),
    make(3, { notify_date: '2026-09-24', status: 'W_PORCIE', warehouse_name: 'DLT' }),
  ]
  it('Dzień: rosnąco, bez daty na końcu', () => {
    expect(groupContainers(items, 'weekday').map(g => g.key)).toEqual(['2026-09-24', '2026-09-26', ''])
  })
  it('Etap: kolejność cyklu życia', () => {
    expect(groupContainers(items, 'status').map(g => g.key)).toEqual(['W_PORCIE', 'AWIZOWANY'])
  })
  it('Magazyn: malejąco wg liczby', () => {
    expect(groupContainers(items, 'warehouse').map(g => [g.key, g.items.length]))
      .toEqual([['DLT', 2], ['ACME', 1]])
  })
})

describe('selectedLabel', () => {
  it('odmiana PL: 1 zaznaczony, 2–4 zaznaczone (poza 12–14), reszta zaznaczonych', () => {
    expect([1, 2, 4, 5, 12, 22, 25].map(n => selectedLabel(n, 'pl'))).toEqual([
      '1 zaznaczony', '2 zaznaczone', '4 zaznaczone', '5 zaznaczonych',
      '12 zaznaczonych', '22 zaznaczone', '25 zaznaczonych'])
    expect(selectedLabel(3, 'en')).toBe('3 selected')
  })
})

describe('rowOrder', () => {
  it('grupy po kolei, w grupie sekcje planowania (Potwierdzone → Propozycje), potem sort', () => {
    const groups = [
      { key: 'a', items: [make(1, { planning_status: 'PROPOZYCJA' }), make(2, { planning_status: 'POTWIERDZONE' })] },
      { key: 'b', items: [make(4), make(3)] },
    ]
    const byId = (xs: Container[]) => [...xs].sort((p, q) => p.id - q.id)
    expect(rowOrder(groups, byId)).toEqual([2, 1, 3, 4])
  })
})

describe('etykiety wiersza', () => {
  it('demurrage: dziś „0 d" (nie „+0 d"), po terminie „+N d", przed terminem „N d"', () => {
    expect(demurrageLabel(0, '{n} d')).toBe('0 d')
    expect(demurrageLabel(-3, '{n} d')).toBe('+3 d')
    expect(demurrageLabel(2, '{n} d')).toBe('2 d')
  })
  it('status bez prefiksu numeru etapu', () => {
    expect(stageName('4 · Transport morski')).toBe('Transport morski')
    expect(stageName('10 · Przyjęcie na magazyn')).toBe('Przyjęcie na magazyn')
    expect(stageName('Inne')).toBe('Inne')
  })
})
