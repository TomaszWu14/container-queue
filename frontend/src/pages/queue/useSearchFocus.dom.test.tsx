// @vitest-environment jsdom
// Wybór podpowiedzi → rekord w kolejce: kontener w zwiniętej grupie/sekcji = rozwinięcie
// (bez zmiany filtrów); spoza widoku = zawężenie do numeru i karta, gdy nadal go brak;
// dostawca/statek = filtr na cały zakres.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, renderHook } from '@testing-library/react'
import type { Container } from '../../types'
import { useSearchFocus } from './useSearchFocus'
import type { Suggestion } from './SearchSuggest'

afterEach(cleanup)

const c = { id: 5, planning_status: 'WYSLANE' } as unknown as Container
const base: Suggestion = { type: 'container', label: 'MSDU0806613', container_id: 5, container_no: 'MSDU0806613',
  notify_date: null, warehouse: null, vessel: null, supplier_id: 3 }

function setup(over: Partial<Parameters<typeof useSearchFocus>[0]> = {}) {
  const p = {
    containers: [c], loading: false, groups: [{ key: '2026-10-14', items: [c] }],
    collapsed: new Set(['2026-10-14']), setCollapsed: vi.fn(),
    collapsedPlanning: ['WYSLANE'], togglePlanSection: vi.fn(),
    searchParams: new URLSearchParams(), patchParams: vi.fn(), setExpandedId: vi.fn(), navigate: vi.fn(),
    ...over,
  }
  const { result, rerender, unmount } = renderHook(props => useSearchFocus(props), { initialProps: p })
  return { p, pick: result.current, rerender, unmount }
}

describe('useSearchFocus', () => {
  it('kontener w zwiniętej grupie i sekcji: rozwija je i wiersz, bez zmiany filtrów', () => {
    const { p, pick } = setup()
    pick(base)
    expect(p.setCollapsed).toHaveBeenCalled()
    expect(p.togglePlanSection).toHaveBeenCalledWith('WYSLANE')
    expect(p.setExpandedId).toHaveBeenCalledWith(5)
    expect(p.patchParams).not.toHaveBeenCalled()
  })

  it('kontener spoza widoku: szukaj=numer na całym zakresie, po nowej liście brak → karta', () => {
    const { p, pick, rerender } = setup({ groups: [] })
    pick(base)
    expect(p.patchParams).toHaveBeenCalledWith(expect.objectContaining(
      { szukaj: 'MSDU0806613', okres: 'all', status: '', widok: '' }))
    rerender({ ...p, containers: [] })            // nowa (pusta) lista po przefiltrowaniu
    expect(p.navigate).toHaveBeenCalledWith('/kontenery/5')
  })

  it('dostawca → filtr dostawcy; statek/PO → wyszukiwanie po etykiecie', () => {
    const { p, pick } = setup()
    pick({ ...base, type: 'supplier', label: 'ACME' })
    expect(p.patchParams).toHaveBeenLastCalledWith(expect.objectContaining({ dostawca: '3', szukaj: '', okres: 'all' }))
    pick({ ...base, type: 'vessel', label: 'MV DEMO ATLAS' })
    expect(p.patchParams).toHaveBeenLastCalledWith(expect.objectContaining({ szukaj: 'MV DEMO ATLAS', dostawca: '' }))
  })

  it('odmontowanie przed przewinięciem kasuje timer — bez dostępu do DOM po zamknięciu kolejki', () => {
    vi.useFakeTimers()
    try {
      const query = vi.spyOn(document, 'querySelector')
      const { pick, unmount } = setup()
      pick(base)
      unmount()
      vi.runAllTimers()
      expect(query).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
      vi.restoreAllMocks()
    }
  })
})
