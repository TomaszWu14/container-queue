// @vitest-environment jsdom
// Strażnik (2026-09-30): „jak zwinę wszystkie wiersze z pozycjami, to nie mogę rozwinąć jednego dnia".
// Przycisk „Propozycje (n)" zwija sekcję GLOBALNIE (wszystkie dni); strzałka dnia przełączała
// tylko zwinięcie grupy, więc dzień nigdy nie pokazywał wierszy. Strzałka ma otworzyć ten jeden dzień.
import { createContext, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render } from '@testing-library/react'
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
import { useGroupCollapse } from './useGroupCollapse'
import type { Container } from '../../types'

const cont = (id: number, planning_status = 'PROPOZYCJA') =>
  ({ id, container_no: `C${id}`, status: 'W_PORCIE', warehouse_name: 'DLT', customs_status: 'BRAK', planning_status }) as unknown as Container

function Harness({ groups, groupBy = 'weekday' }: { groups: { key: string; items: Container[] }[]; groupBy?: string }) {
  // jak useViewPrefs: globalna lista zwiniętych sekcji planowania
  const [collapsedPlanning, setCP] = useState<string[]>([])
  const toggleGlobal = (s: string) => setCP(p => (p.includes(s) ? p.filter(v => v !== s) : [...p, s]))
  const gc = useGroupCollapse(collapsedPlanning, toggleGlobal, groupBy)
  const x = {
    groups, groupBy, collapsed: gc.collapsed, toggleGroup: gc.toggleGroup, opened: gc.opened,
    collapsedPlanning, togglePlanSection: gc.togglePlanSection,
    selectable: false, compact: false, showCompany: false, dense: true,
    columns: new Set(['no']), sortBy: [], fillMap: {}, openCells: new Set(),
    conflictIcon: () => null, mv: { selected: new Set(), moveActive: false, dragId: null },
    watched: new Set(), sortItems: (i: Container[]) => i, expandedId: null, drawerId: null,
    warehouseKeys: [], cumByDay: new Map(), limitFor: () => null,
  } as unknown as TableCtx
  return <MemoryRouter><EnterpriseTable x={x} /></MemoryRouter>
}

const setup = (groupBy?: string, extra: Container[] = []) => {
  const groups = [
    { key: groupBy === 'warehouse' ? 'DLT' : '2026-09-28', items: [cont(1), cont(2)] },
    { key: groupBy === 'warehouse' ? 'ACME' : '2026-09-29', items: [cont(3), ...extra] },
  ]
  const r = render(<Harness groups={groups} groupBy={groupBy} />)
  const bodies = () => [...r.container.querySelectorAll('tbody.kq-group')] as HTMLElement[]
  const rows = (i: number) => [...bodies()[i].querySelectorAll('td.kq-c-no')].length
  const caret = (i: number) => bodies()[i].querySelector('.kq-caret') as HTMLButtonElement
  const plan = (i: number) => bodies()[i].querySelector('.kq-gplan, .kq-plan-btn') as HTMLButtonElement
  return { rows, caret, plan }
}

describe('kolejka — zwijanie dnia po „zwiń wszystkie" propozycje', () => {
  for (const groupBy of ['weekday', 'warehouse']) {
    it(`strzałka otwiera jeden dzień, „rozwiń wszystkie" dalej działa (${groupBy})`, () => {
      const { rows, caret, plan } = setup(groupBy)
      expect([rows(0), rows(1)]).toEqual([2, 1])
      fireEvent.click(plan(0))   // „Propozycje" = zwiń we wszystkich dniach
      expect([rows(0), rows(1)]).toEqual([0, 0])
      expect(caret(1).getAttribute('aria-expanded')).toBe('false')
      fireEvent.click(caret(1))   // rozwiń tylko drugi dzień
      expect([rows(0), rows(1)]).toEqual([0, 1])
      expect(caret(1).getAttribute('aria-expanded')).toBe('true')
      expect(plan(1).getAttribute('aria-expanded')).toBe('true')
      fireEvent.click(caret(1))   // i zwiń go z powrotem
      expect([rows(0), rows(1)]).toEqual([0, 0])
      fireEvent.click(caret(1))
      fireEvent.click(plan(0))   // „Propozycje" ponownie = rozwiń wszystkie
      expect([rows(0), rows(1)]).toEqual([2, 1])
    })
  }

  it('sekcja w ręcznie otwartym dniu zwija tylko ten dzień', () => {
    const { rows, caret, plan } = setup()
    fireEvent.click(plan(0))
    fireEvent.click(caret(1))
    fireEvent.click(plan(1))
    expect([rows(0), rows(1)]).toEqual([0, 0])
    expect(caret(1).getAttribute('aria-expanded')).toBe('false')
  })

  it('dzień z kilkoma sekcjami: otwarty strzałką pokazuje też zwiniętą globalnie', () => {
    const { rows, caret, plan } = setup('weekday', [cont(4, 'POTWIERDZONE')])
    expect([rows(0), rows(1)]).toEqual([2, 2])
    fireEvent.click(plan(0))   // zwiń Propozycje (dzień 1 ma tylko je)
    expect([rows(0), rows(1)]).toEqual([0, 1])
    expect(caret(1).getAttribute('aria-expanded')).toBe('true')   // Potwierdzone nadal widać
    fireEvent.click(caret(0))
    expect([rows(0), rows(1)]).toEqual([2, 1])
  })
})
