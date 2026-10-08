// @vitest-environment jsdom
// Zakładka „Porty kontenerowe" w Master data + fallback statycznej listy CPORTS na mapie.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { mdAt } from './mdRoute.testutil'
import MasterDataPage from './MasterDataPage'
import MapDecorOverlay from './tracking/MapDecor'
import { CPORTS_MINOR } from './tracking/mapStatic'
import { WORLD_W } from '../worldmap'

vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../App', () => ({ useUser: () => ({ role: 'admin' }) }))

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({ api: { get: apiGet } }))

function mockApi(map: Record<string, unknown>) {
  apiGet.mockImplementation((url: string) => {
    const key = Object.keys(map).find(k => url.startsWith(k))
    return key ? Promise.resolve(map[key]) : Promise.reject(new Error('unmocked ' + url))
  })
}

afterEach(() => { cleanup(); apiGet.mockReset() })

describe('Master data — porty kontenerowe', () => {
  it('renderuje wiersze słownika, kolumnę współrzędnych i szukajkę', async () => {
    mockApi({
      '/api/companies': [],
      '/api/suppliers': [],
      '/api/container-ports': [
        { id: 1, code: 'ESIBZ', name: 'IBIZA', country_code: 'ES', country_name: 'Spain',
          lat: 38.9, lon: 1.43, is_active: true },
        { id: 2, code: 'ZZICB', name: 'ICD AHMEDABAD', country_code: 'ID',
          country_name: 'Indonesia', lat: null, lon: null, is_active: true },
      ],
    })
    render(mdAt('porty-kontenerowe', <MasterDataPage />))

    await screen.findByText('IBIZA')
    expect(screen.getByText('ICD AHMEDABAD')).toBeTruthy()
    expect(screen.getByText('38.9, 1.43')).toBeTruthy()      // współrzędne
    // port bez dopasowania → kreska w kolumnie współrzędnych
    const rows = document.querySelectorAll('tbody tr')
    expect(rows[1].textContent).toContain('—')

    fireEvent.change(screen.getByPlaceholderText('mdSearch'), { target: { value: 'ibiza' } })
    await waitFor(() => expect(screen.queryByText('ICD AHMEDABAD')).toBeNull())
    expect(screen.getByText('IBIZA')).toBeTruthy()
  })
})

describe('MapDecor — warstwa wszystkich portów', () => {
  const view = { x: 0, y: 0, w: WORLD_W }
  const base = {
    view, showNames: false, showLabels: false, showAllPorts: true,
    portCounts: new Map<string, number>(),
  }

  it('pusta lista ze słownika → fallback na statyczną CPORTS_MINOR', () => {
    const { container } = render(
      <svg><MapDecorOverlay {...base} allPortsList={[]} /></svg>)
    expect(container.querySelectorAll('circle').length)
      .toBeGreaterThanOrEqual(CPORTS_MINOR.length)
  })

  it('lista ze słownika zastępuje statyczną (kropka + tooltip z nazwą)', () => {
    const { container } = render(
      <svg><MapDecorOverlay {...base}
        allPortsList={[{ name: 'IBIZA', cc: 'ES', lon: 1.43, lat: 38.9 }]} /></svg>)
    // 1 port + 3 magazyny (WAREHOUSES rysują własne circle)
    expect(container.textContent).toContain('IBIZA · ES')
    expect(container.querySelectorAll('circle').length).toBeLessThan(CPORTS_MINOR.length)
  })
})
