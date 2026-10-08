import { describe, expect, it } from 'vitest'
import type { Container } from '../../../types'
import { applyColFilters, columnValues, initialChecked, parseColFilters, toFilter } from './values'

const t = (k: string) => k
const c = (o: Partial<Container>) => o as Container

describe('filtry kolumn — logika', () => {
  it('daty chronologicznie, (Puste) na końcu, etykieta jak w komórce', () => {
    const rows = [c({ notify_date: '2026-10-02' }), c({ notify_date: null }), c({ notify_date: '2026-09-30' })]
    expect(columnValues('notify', rows, '2026-09-30', t).map(o => o.key)).toEqual(['2026-09-30', '2026-10-02', ''])
  })

  it('komórka wielowartościowa: wiersz liczy się pod każdym numerem i przechodzi, gdy któryś wybrany', () => {
    const rows = [c({ order_numbers: '450001, 450002' }), c({ order_numbers: '450002' })]
    expect(columnValues('order', rows, '', t).map(o => [o.key, o.count])).toEqual([['450001', 1], ['450002', 2]])
    expect(applyColFilters(rows, { order: { in: ['450001'] } }, '')).toHaveLength(1)
  })

  it('zapis krótszej listy: jedna odznaczona z wielu → out; wszystko → brak filtra', () => {
    const opts = ['a', 'b', 'c'].map(key => ({ key, label: key, count: 1 }))
    expect(toFilter(new Set(['a', 'b']), opts)).toEqual({ out: ['c'] })
    expect(toFilter(new Set(['a']), opts)).toEqual({ in: ['a'] })
    expect(toFilter(new Set(['a', 'b', 'c']), opts)).toBeNull()
    expect([...initialChecked({ out: ['c'] }, opts)]).toEqual(['a', 'b'])
  })

  it('URL: nieznana kolumna i zły kształt pomijane', () => {
    expect(parseColFilters('{"vessel":{"in":["X",1]},"hack":{"in":["y"]},"eta":5}')).toEqual({ vessel: { in: ['X'] } })
    expect(parseColFilters('[1]')).toEqual({})
  })
})
