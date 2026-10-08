// @vitest-environment jsdom
// Strażnik pustych kolumn (audyt UI A9/B35/C17 — UX-022, UX-032, UX-035): kolumna bez wartości w całej
// widocznej tabeli NIE jest renderowana (dawniej zwężona do 32px z nagłówkiem „—", który nic nie mówił);
// lista ukrytych nazw trafia do rodzica (stopka kolejki), kolumny z danymi zostają bez zmian.
import { createContext } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../i18n', () => ({
  useT: () => (key: string) => key,
  LangContext: createContext({ lang: 'pl' }),
  localeFor: () => 'pl-PL',
}))
vi.mock('../ContainerDetailPanel', () => ({ default: () => null }))

import EnterpriseTable from './EnterpriseTable'
import type { TableCtx } from './EnterpriseTable'
import type { Container } from '../../types'

const row = (id: number) => ({
  id, container_no: `MSCU000000${id}`, status: 'W_PORCIE', warehouse_name: 'DLT',
  supplier_name: null, vessel: 'MV DEMO ATLAS', customs_status: 'BRAK',
}) as unknown as Container

const x = {
  groups: [{ key: 'X', items: [row(1), row(2)] }], groupBy: 'warehouse', collapsed: new Set(),
  collapsedPlanning: [], selectable: false, compact: false, showCompany: false, dense: true,
  columns: new Set(['no', 'supplier', 'vessel']), sortBy: [], fillMap: {}, openCells: new Set(),
  conflictIcon: () => null, mv: { selected: new Set(), moveActive: false, dragId: null },
  watched: new Set(), sortItems: (i: Container[]) => i, expandedId: null, drawerId: null,
  warehouseKeys: [], cumByDay: new Map(), limitFor: () => null,
} as unknown as TableCtx

describe('kolejka — pusta kolumna', () => {
  it('pusta w całej tabeli: bez nagłówka „—" i bez komórek; nazwa zgłoszona rodzicowi; pełne kolumny bez zmian', () => {
    const onHiddenCols = vi.fn()
    const { container } = render(<MemoryRouter><EnterpriseTable x={{ ...x, onHiddenCols }} /></MemoryRouter>)
    expect(container.querySelector('th.kq-h-supplier')).toBeNull()
    expect(container.querySelector('td.kq-c-supplier')).toBeNull()
    const heads = [...container.querySelectorAll('thead th')].map(th => th.textContent)
    expect(heads).not.toContain('—')
    expect(onHiddenCols).toHaveBeenLastCalledWith(['supplier'])

    const full = container.querySelector('th.kq-h-vessel')!
    expect(full.textContent).toBe('vessel')
    expect(container.querySelector('td.kq-c-vessel')!.textContent).toBe('MV DEMO ATLAS')
    // każda <col> danych ma szerokość w % (żadnej sztywnej 32px)
    const widths = [...container.querySelectorAll('col')].slice(1, -1).map(c => (c as HTMLElement).style.width)
    expect(widths.every(w => w.endsWith('%'))).toBe(true)
  })
})
