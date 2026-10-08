// @vitest-environment jsdom
// Mini-kafelki dokumentów w kolejce (spec 2026-10-06 decyzja 28): jedno żądanie bulk na listę,
// pasek PI·CI·PL·BL·SAD + „⏳ N” w wierszu, zakładki „Braki dokumentów” / „Czeka w poczekalni”.
import { createContext } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, renderHook, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const get = vi.fn()
vi.mock('../../api', () => ({ api: { get: (url: string) => get(url) } }))
vi.mock('../../i18n', () => ({
  useT: () => (key: string) => key,
  LangContext: createContext({ lang: 'pl' }),
  localeFor: () => 'pl-PL',
}))
vi.mock('../ContainerDetailPanel', () => ({ default: () => null }))

import EnterpriseTable from './EnterpriseTable'
import type { TableCtx } from './EnterpriseTable'
import { useDocTiles } from './docTiles'
import type { DocTilesMap } from './docTiles'
import { matchesView, viewCounts } from './enterprise'
import type { Container } from '../../types'

const row = (id: number) => ({
  id, container_no: `MSCU000000${id}`, status: 'W_PORCIE', warehouse_name: 'DLT', customs_status: 'BRAK',
}) as unknown as Container

const BULK = {
  1: { codes: { PI: 'ok', CI: 'warn', PL: 'present', BL: 'none', SAD: 'bad' }, missing: ['BL'], intake_pending: 0 },
  2: { codes: { PI: 'ok', CI: 'ok', PL: 'ok', BL: 'present', SAD: 'none' }, missing: [], intake_pending: 3 },
  3: { codes: { PI: 'ok', CI: 'ok', PL: 'ok', BL: 'present', SAD: 'ok' }, missing: [], intake_pending: 0 },
}

describe('kolejka — mini-kafelki dokumentów', () => {
  it('jedno żądanie bulk dla całej listy → mapa id', async () => {
    get.mockResolvedValue(BULK)
    const { result } = renderHook(() => useDocTiles([1, 2, 3], true))
    await waitFor(() => expect(result.current[2]?.intake_pending).toBe(3))
    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith('/api/document-tiles?ids=1,2,3')
  })

  it('wiersz pokazuje 5 kwadracików ze stanem, brak na czerwono i znacznik poczekalni', () => {
    const x = {
      groups: [{ key: 'X', items: [row(1), row(2)] }], groupBy: 'warehouse', collapsed: new Set(),
      collapsedPlanning: [], selectable: false, compact: false, showCompany: false, dense: true,
      columns: new Set(['no', 'docs']), sortBy: [], fillMap: {}, openCells: new Set(), docTiles: BULK,
      conflictIcon: () => null, mv: { selected: new Set(), moveActive: false, dragId: null },
      watched: new Set(), sortItems: (i: Container[]) => i, expandedId: null, drawerId: null,
      warehouseKeys: [], cumByDay: new Map(), limitFor: () => null,
    } as unknown as TableCtx
    const { container } = render(<MemoryRouter><EnterpriseTable x={x} /></MemoryRouter>)
    const cells = container.querySelectorAll('td.kq-c-docs')
    expect(cells).toHaveLength(2)
    const sq = [...cells[0].querySelectorAll('.dt-sq')]
    expect(sq.map(s => s.textContent)).toEqual(['PI', 'CI', 'PL', 'BL', 'SAD'])
    expect(sq[3].className).toContain('miss')
    expect(sq[4].className).toContain('st-bad')
    expect(cells[0].querySelector('.dt-intake')).toBeNull()
    expect(cells[1].querySelector('.dt-intake')!.textContent).toContain('3')
  })

  it('zakładki Braki / Poczekalnia zawężają wiersze', () => {
    const rows = [row(1), row(2), row(3), row(4)]   // 4 = jeszcze bez danych
    const docs = BULK as unknown as DocTilesMap
    const ids = (v: 'docsMissing' | 'intake') =>
      rows.filter(c => matchesView(c, v, '2026-10-07', new Set(), docs)).map(c => c.id)
    expect(ids('docsMissing')).toEqual([1])
    expect(ids('intake')).toEqual([2])
    const counts = viewCounts(rows, '2026-10-07', new Set(), docs)
    expect([counts.all, counts.docsMissing, counts.intake]).toEqual([4, 1, 1])
  })
})
