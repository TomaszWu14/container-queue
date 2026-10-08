// @vitest-environment jsdom
// Strażnik (2026-09-29): przepisanie tabeli na Kolejkę Enterprise zgubiło kopiowanie numerów.
// Nr kontenera, zamówienie (PO) i nr dostawy mają przycisk ⧉ z wartością komórki;
// „kopiuj wszystkie” PO po rozwinięciu (strzałka w nagłówku kolumny, 2026-10-01).
import { createContext } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../i18n', () => ({
  useT: () => (key: string) => key,
  LangContext: createContext({ lang: 'pl' }),
  localeFor: () => 'pl-PL',
}))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('../ContainerDetailPanel', () => ({ default: () => null }))

import EnterpriseTable from './EnterpriseTable'
import type { TableCtx } from './EnterpriseTable'
import type { Container } from '../../types'

const c = {
  id: 1, container_no: 'FFAU1005416', status: 'W_PORCIE', warehouse_name: 'DLT', customs_status: 'BRAK',
  order_numbers: '4500623852-2\n4500622711', incoming_delivery_no: '180001234',
} as unknown as Container

const x = {
  groups: [{ key: 'X', items: [c] }], groupBy: 'warehouse', collapsed: new Set(),
  collapsedPlanning: [], selectable: false, compact: false, showCompany: false, dense: true,
  columns: new Set(['no', 'order', 'incomingNo']), sortBy: [], fillMap: {}, openCells: new Set(),
  conflictIcon: () => null, mv: { selected: new Set(), moveActive: false, dragId: null },
  watched: new Set(), sortItems: (i: Container[]) => i, expandedId: null, drawerId: null,
  warehouseKeys: [], cumByDay: new Map(), limitFor: () => null,
} as unknown as TableCtx

describe('kolejka — kopiowanie numerów', () => {
  it('⧉ w kolumnach Nr kontenera, Zamówienie i Nr dostawy', () => {
    const { container } = render(<MemoryRouter><EnterpriseTable x={x} /></MemoryRouter>)
    const copies = (col: string) => [...container.querySelectorAll(`td.kq-c-${col} .copy-btn`)]
      .map(b => b.getAttribute('data-copy'))
    expect(copies('no')).toEqual(['FFAU1005416'])
    expect(copies('order')).toEqual(['4500623852-2'])   // zwinięta: „kopiuj wszystkie” po rozwinięciu
    expect(copies('incomingNo')).toEqual(['180001234'])
  })

  it('strzałka w nagłówku rozwija całą kolumnę (wszystkie numery + kopiuj wszystkie)', () => {
    const toggleColOpen = vi.fn()
    const open = { ...x, openCols: new Set(['order']), toggleColOpen } as unknown as TableCtx
    const { container } = render(<MemoryRouter><EnterpriseTable x={open} /></MemoryRouter>)
    const copies = [...container.querySelectorAll('td.kq-c-order .copy-btn')].map(b => b.getAttribute('data-copy'))
    expect(copies).toEqual(['4500623852-2', '4500622711', '4500623852-2\n4500622711'])
    const btn = container.querySelector<HTMLButtonElement>('th .kq-h-expand')!
    expect(btn.getAttribute('aria-pressed')).toBe('true')
    btn.click()
    expect(toggleColOpen).toHaveBeenCalledWith('order')
  })
})
