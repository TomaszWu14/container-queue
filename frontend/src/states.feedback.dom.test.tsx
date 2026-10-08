// @vitest-environment jsdom
// Stany i komunikaty (audyt UI A24/B22/C7 — UX-014, UX-027, UX-044):
// - oś zdarzeń: koniec wolnych dni pokazuje start w dd.mm.rrrr i „+ 5 dni”, nie ISO „2026-07-23 +5d”,
// - Analityka: pusty wykres przepustowości i pusta lista dostawców mają komunikat zamiast pustki,
// - Śledzenie: awaria warstwy AIS to wspólny baner błędu NAD mapą (z „Spróbuj ponownie”), nie szary
//   pasek mono przyklejony na mapie, zasłaniający przycisk 2D.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiGet } = vi.hoisted(() => ({
  apiGet: vi.fn((url: string): Promise<unknown> => {
    if (url === '/api/tracking/vessels') return Promise.reject(new Error('fail'))
    if (url === '/api/tracking/map') return Promise.resolve({ points: [], unlocated: [], tracked: 3, total: 3 })
    if (url === '/api/analytics/operational') return Promise.resolve({
      total: 4, by_status: { W_PORCIE: 4 }, avg_lead_time_days: null, avg_unload_minutes: null,
      throughput: ['2026-04', '2026-05', '2026-06'].map(month => ({ month, count: 0 })),
      top_suppliers: [], top_warehouses: [{ name: 'DLT', count: 4 }],
    })
    return Promise.resolve([])
  }),
}))
vi.mock('./api', () => ({
  api: { get: apiGet, post: vi.fn(() => Promise.resolve({})), upload: vi.fn() },
  downloadFile: vi.fn(),
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: 'admin' }) }))
vi.mock('./worldmap', () => ({ WORLD_W: 100, WORLD_H: 100, WORLD_PATH: '' }))
vi.mock('./pages/tracking/GlobeView', () => ({ default: () => null }))

import ContainerTimeline from './pages/tracking/ContainerTimeline'
import AnalitykaPage from './pages/AnalitykaPage'
import TrackingPage from './pages/TrackingPage'

afterEach(cleanup)

describe('stany i komunikaty', () => {
  it('oś zdarzeń: koniec wolnych dni w dd.mm.rrrr i „+ N dni”', () => {
    render(<ContainerTimeline containerId={1} entries={[
      { kind: 'planned', code: 'DEMURRAGE', title: 'x', location: '2026-07-23 +5d',
        at: '2026-07-28T00:00:00', estimated: true, source: 'system' },
      { kind: 'planned', code: 'DEMURRAGE', title: 'x', location: '2026-07-23 +1d',
        at: '2026-07-24T00:00:00', estimated: true, source: 'system' },
    ]} />)
    expect(screen.getByText('od 23.07.2026 + 5 dni')).toBeTruthy()
    expect(screen.getByText('od 23.07.2026 + 1 dzień')).toBeTruthy()
    expect(screen.queryByText(/2026-07-23/)).toBeNull()
  })

  it('Analityka: pusty wykres i brak dostawców mają komunikat', async () => {
    render(<AnalitykaPage />)
    expect(await screen.findByText('Brak dostarczonych kontenerów w tym okresie.')).toBeTruthy()
    expect(screen.getByText('Brak danych o dostawcach.')).toBeTruthy()
    // lista z danymi bez zmian
    expect(screen.getByText((_, el) => el?.tagName === 'LI' && el.textContent === 'DLT: 4')).toBeTruthy()
  })

  it('Śledzenie: błąd warstwy AIS jako baner nad mapą z ponowieniem', async () => {
    render(<MemoryRouter><TrackingPage /></MemoryRouter>)
    const msg = await screen.findByText('Warstwa statków niedostępna — spróbuj odświeżyć')
    const banner = msg.closest('.load-error')!
    expect(banner).not.toBeNull()
    expect(banner.closest('.map-wrap')).toBeNull()
    expect(banner.querySelector('button')!.textContent).toBe('Spróbuj ponownie')
    const calls = apiGet.mock.calls.filter(([u]) => u === '/api/tracking/vessels').length
    banner.querySelector('button')!.click()
    await waitFor(() => expect(apiGet.mock.calls.filter(([u]) => u === '/api/tracking/vessels').length)
      .toBeGreaterThan(calls))
  })
})
