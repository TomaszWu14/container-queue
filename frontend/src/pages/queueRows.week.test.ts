import { describe, it, expect } from 'vitest'
import { groupByWeek, groupByKey } from './queueRows'
import type { DayRow } from './queueRows'
import type { Container } from '../types'

const day = (d: string, n: number): DayRow =>
  ({ day: d, items: Array.from({ length: n }, (_, i) => ({ id: i } as Container)) })

const cont = (over: Record<string, unknown>): Container => ({ id: 0, ...over } as Container)
const STATUS_ORDER = ['ZAPOWIEDZIANY', 'W_TRANSPORCIE', 'W_PORCIE'] as const

describe('groupByKey', () => {
  it('Magazyn: grupuje po warehouse_name, sort malejąco wg liczby, pusty → sentinel', () => {
    const rows: DayRow[] = [{ day: '2026-09-17', items: [
      cont({ warehouse_name: 'DLT' }), cont({ warehouse_name: 'ACME' }),
      cont({ warehouse_name: 'DLT' }), cont({ warehouse_name: '' }),
    ] }]
    const g = groupByKey(rows, 'warehouse', STATUS_ORDER, 'BEZ')
    expect(g.map(x => [x.key, x.items.length])).toEqual([['DLT', 2], ['ACME', 1], ['BEZ', 1]])
  })

  it('Status: kolejność wg cyklu życia, nieznane na końcu', () => {
    const rows: DayRow[] = [{ day: '2026-09-17', items: [
      cont({ status: 'W_PORCIE' }), cont({ status: 'ZAPOWIEDZIANY' }),
      cont({ status: 'COS_INNEGO' }), cont({ status: 'W_TRANSPORCIE' }),
    ] }]
    const g = groupByKey(rows, 'status', STATUS_ORDER, 'BEZ')
    expect(g.map(x => x.key)).toEqual(['ZAPOWIEDZIANY', 'W_TRANSPORCIE', 'W_PORCIE', 'COS_INNEGO'])
  })
})

describe('groupByWeek', () => {
  it('grupuje dni po tygodniu ISO — suma i zakres pon–niedz jak w makiecie (T38)', () => {
    // 2026-09-17 (czw) + 2026-09-18 (pt) → tydzień 38; 2026-09-21 (pon) → tydzień 39
    const g = groupByWeek([day('2026-09-17', 4), day('2026-09-18', 3), day('2026-09-21', 2)])
    expect(g.map(x => x.week)).toEqual([38, 39])
    expect(g[0].total).toBe(7)
    expect(g[0].days.length).toBe(2)
    expect([g[0].start, g[0].end]).toEqual(['2026-09-14', '2026-09-20'])
    expect(g[1].total).toBe(2)
    expect(g[1].days.length).toBe(1)
  })

  it('dzień bez daty trafia do osobnego bloku bez tygodnia', () => {
    const g = groupByWeek([day('2026-09-17', 1), { day: '', items: [{ id: 9 } as Container] }])
    expect(g[1].week).toBeNull()
    expect(g[1].total).toBe(1)
  })
})
