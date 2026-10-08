// @vitest-environment jsdom
// Przełącznik 2D/3D na /sledzenie: globus domyślny, wybór zapamiętany
// w localStorage, płaska mapa (SVG) pod przełącznikiem.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn((url: string) => {
    if (url === '/api/tracking/map') return Promise.resolve(
      // tracked > 0: pusta mapa zwija się do pustego stanu (C30) — tu testujemy samą mapę
      { points: [], unlocated: [], tracked: 1, total: 1 })
    return Promise.resolve([])
  }),
  apiPost: vi.fn(() => Promise.resolve({})),
}))

vi.mock('./api', () => ({
  api: { get: apiGet, post: apiPost },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: 'admin' }) }))
vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
vi.mock('./worldmap', () => ({ WORLD_W: 100, WORLD_H: 50, WORLD_PATH: '' }))

import TrackingPage from './pages/TrackingPage'

afterEach(() => { cleanup(); localStorage.clear(); apiGet.mockClear() })

describe('TrackingPage — przełącznik mapy 2D/3D', () => {
  it('domyślnie 3D: globus (fallback bez WebGL w jsdom), bez SVG mapy', async () => {
    const { container } = render(<MemoryRouter><TrackingPage /></MemoryRouter>)
    // GlobeView jest lazy — czekamy aż chunk się wczyta
    await waitFor(() => expect(container.querySelector('[data-testid="globe-fallback"]')).toBeTruthy())
    expect(container.querySelector('svg.world-map')).toBeNull()
    const btn = container.querySelector('.map-mode-toggle') as HTMLButtonElement
    expect(btn.textContent).toContain('2D')
  })

  it('klik przełącznika → mapa 2D + zapis w localStorage', async () => {
    const { container } = render(<MemoryRouter><TrackingPage /></MemoryRouter>)
    await waitFor(() => expect(container.querySelector('.map-mode-toggle')).toBeTruthy())
    fireEvent.click(container.querySelector('.map-mode-toggle')!)
    expect(container.querySelector('svg.world-map')).toBeTruthy()
    expect(localStorage.getItem('trackingMapMode')).toBe('2d')
  })

  it('zapamiętany tryb 2D → SVG od razu, przycisk oferuje 3D', () => {
    localStorage.setItem('trackingMapMode', '2d')
    const { container } = render(<MemoryRouter><TrackingPage /></MemoryRouter>)
    expect(container.querySelector('svg.world-map')).toBeTruthy()
    const btn = container.querySelector('.map-mode-toggle') as HTMLButtonElement
    expect(btn.textContent).toContain('3D')
  })
})
