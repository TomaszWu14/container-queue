// @vitest-environment jsdom
// Strażnik kolejności kolumn kolejki: przeciąganie nagłówka przestawia kolumnę (nagłówki i komórki),
// kolejność idzie do profilu konta (setPref) i wraca po ponownym montażu; Nr kontenera zawsze pierwszy;
// ↑/↓ i „Przywróć domyślną kolejność" w menu „Widok"; klik w etykietę dalej sortuje, lejek dalej filtruje.
import { createContext } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../i18n', () => ({
  useT: () => (key: string) => key,
  LangContext: createContext({ lang: 'pl' }),
  localeFor: () => 'pl-PL',
}))
vi.mock('../ContainerDetailPanel', () => ({ default: () => null }))
// useViewPrefs pobiera obserwowane — konkretne kształty, nie ogólny mock (losowe TypeError w CI)
vi.mock('../../api', () => ({ api: { get: vi.fn(() => Promise.resolve([])), post: vi.fn(() => Promise.resolve({})) } }))
const setPref = vi.fn((k: string, v: string) => localStorage.setItem(k, v))
vi.mock('../../prefs', () => ({ setPref: (k: string, v: string) => setPref(k, v), cancelPendingPrefs: () => {} }))

import EnterpriseTable from './EnterpriseTable'
import type { TableCtx } from './EnterpriseTable'
import { ViewOptions } from './ViewControls'
import { useViewPrefs } from './useViewPrefs'
import type { Container } from '../../types'

const row = (id: number) => ({
  id, container_no: `MSCU000000${id}`, status: 'W_PORCIE', warehouse_name: 'DLT',
  supplier_name: `Dostawca ${id}`, vessel: `STATEK ${id}`, customs_status: 'BRAK', eta: '2026-10-01',
}) as unknown as Container

const toggleSort = vi.fn()
const base = {
  groups: [{ key: 'X', items: [row(1), row(2)] }], groupBy: 'warehouse', collapsed: new Set(),
  collapsedPlanning: [], selectable: false, compact: false, showCompany: false, dense: true,
  sortBy: [], fillMap: {}, openCells: new Set(), toggleSort,
  conflictIcon: () => null, mv: { selected: new Set(), moveActive: false, dragId: null },
  watched: new Set(), sortItems: (i: Container[]) => i, expandedId: null, drawerId: null,
  warehouseKeys: [], cumByDay: new Map(), limitFor: () => null,
  colFilter: { rows: [row(1), row(2)], filters: {}, set: vi.fn(), today: '2026-09-30' },
} as unknown as TableCtx

function Harness() {
  const p = useViewPrefs()
  return (
    <MemoryRouter>
      <EnterpriseTable x={{ ...base, columns: new Set(['no', 'supplier', 'vessel', 'eta']),
                            colOrder: p.colOrder, moveCol: p.moveCol }} />
      <ViewOptions p={p} />
    </MemoryRouter>
  )
}

const heads = (c: HTMLElement) => [...c.querySelectorAll('thead th')].map(th => th.className.match(/kq-h-(\w+)/)?.[1])
  .filter(Boolean)
const cells = (c: HTMLElement) => [...c.querySelector('td.kq-c-no')!.parentElement!
  .querySelectorAll('td[class^="kq-c-"]')].map(td => td.className.replace('kq-c-', ''))
const drag = (from: Element, to: Element, clientX: number) => {
  const dataTransfer = { setData: vi.fn(), effectAllowed: '' }
  fireEvent.dragStart(from, { dataTransfer })
  fireEvent.dragOver(to, { dataTransfer, clientX })
  fireEvent.drop(to, { dataTransfer, clientX })
  fireEvent.dragEnd(from, { dataTransfer })
}

beforeEach(() => { localStorage.clear(); setPref.mockClear(); toggleSort.mockClear() })
afterEach(cleanup)

describe('kolejka — kolejność kolumn', () => {
  it('przeciągnięcie nagłówka przestawia nagłówki i komórki; zapis w profilu i odtworzenie po montażu', () => {
    const { container, unmount } = render(<Harness />)
    expect(heads(container)).toEqual(['no', 'supplier', 'vessel', 'eta'])
    const th = (k: string) => container.querySelector(`th.kq-h-${k}`)!
    // eta upuszczona na lewą połowę „supplier" (jsdom: prostokąt 0×0 → clientX < 0 = przed)
    drag(th('eta'), th('supplier'), -1)
    expect(heads(container)).toEqual(['no', 'eta', 'supplier', 'vessel'])
    expect(cells(container)).toEqual(['no', 'eta', 'supplier', 'vessel'])
    expect(setPref).toHaveBeenCalledWith('kqColOrder', expect.stringContaining('"eta","supplier"'))
    unmount()
    const again = render(<Harness />)
    expect(heads(again.container)).toEqual(['no', 'eta', 'supplier', 'vessel'])
  })

  it('Nr kontenera: nieprzeciągalny i zawsze pierwszy, także po upuszczeniu przed niego', () => {
    const { container } = render(<Harness />)
    const th = (k: string) => container.querySelector(`th.kq-h-${k}`)!
    expect(th('no').getAttribute('draggable')).toBeNull()
    expect(th('vessel').getAttribute('draggable')).toBe('true')
    drag(th('vessel'), th('no'), -1)   // Nr nie jest celem upuszczenia
    drag(th('no'), th('vessel'), 1)    // Nr nie da się ruszyć
    expect(heads(container)[0]).toBe('no')
    expect(heads(container)).toEqual(['no', 'supplier', 'vessel', 'eta'])
    // przyklejony blok (CSS left: 0 / left: SEL_W) zakłada kolejność DOM: wybór, potem Nr
    drag(th('eta'), th('supplier'), -1)
    expect([...container.querySelectorAll('thead th')].slice(0, 2).map(e => e.className.split(' ')[0]))
      .toEqual(['kq-sel', 'kq-h-no'])
    const row = container.querySelector('tr.kq-row')!
    expect([...row.children].slice(0, 2).map(e => e.className)).toEqual(['kq-sel', 'kq-c-no'])
  })

  it('zły kształt / nieznane klucze w profilu: ignorowane, nowe kolumny na domyślnym miejscu', () => {
    localStorage.setItem('kqColOrder', JSON.stringify(['vessel', 42, 'supplier', 'bogus', 'no']))
    const { container } = render(<Harness />)
    // eta spoza zapisu (np. nowa w kodzie) staje za swoim domyślnym poprzednikiem (vessel)
    expect(heads(container)).toEqual(['no', 'vessel', 'eta', 'supplier'])
    cleanup()
    localStorage.setItem('kqColOrder', '{"x":1}')
    expect(heads(render(<Harness />).container)).toEqual(['no', 'supplier', 'vessel', 'eta'])
  })

  it('↑/↓ w menu „Widok" i „Przywróć domyślną kolejność"', () => {
    const { container } = render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'kqColMoveUp: vessel' }))
    expect(heads(container)).toEqual(['no', 'vessel', 'supplier', 'eta'])
    fireEvent.click(screen.getByRole('button', { name: 'kqColMoveDown: vessel' }))
    fireEvent.click(screen.getByRole('button', { name: 'kqColMoveDown: vessel' }))
    expect(heads(container)).toEqual(['no', 'supplier', 'eta', 'vessel'])
    // skraje sekcji zablokowane, Nr bez strzałek
    expect((screen.getByRole('button', { name: 'kqColMoveUp: supplier' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.queryByRole('button', { name: 'kqColMoveUp: containerNo' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'kqColOrderReset' }))
    expect(heads(container)).toEqual(['no', 'supplier', 'vessel', 'eta'])
    expect(localStorage.getItem('kqColOrder')).toBe('null')
  })

  it('klik w etykietę dalej sortuje, lejek otwiera filtr bez sortowania', () => {
    const { container } = render(<Harness />)
    fireEvent.click(container.querySelector('th.kq-h-vessel')!)
    expect(toggleSort).toHaveBeenCalledWith('vessel', false)
    toggleSort.mockClear()
    const funnel = screen.getByRole('button', { name: 'cfFilterBy: vessel' })
    fireEvent.click(funnel)
    expect(funnel.getAttribute('aria-expanded')).toBe('true')
    expect(toggleSort).not.toHaveBeenCalled()
  })
})
