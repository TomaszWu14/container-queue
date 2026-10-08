// @vitest-environment jsdom
// Audyt UX pkt 8 — markery mapy: hover-only tooltip nie działa na dotyku.
// Tap markera ma PRZYPIĄĆ tooltip (nie nawigować), a nawigacja idzie przez CTA.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiGet, apiPost, navigate } = vi.hoisted(() => ({
  apiGet: vi.fn(() => Promise.resolve({
    points: [{
      id: 42, container_no: 'MSKU1', vessel: '', status: 'W_TRANSPORCIE',
      eta: null, etd: null, location: 'Gdańsk', event: 'załadunek',
      occurred_at: null, lat: 54, lon: 18,
    }],
    unlocated: [], tracked: 1, total: 1,
  })),
  apiPost: vi.fn(() => Promise.resolve({})),
  navigate: vi.fn(),
}))

vi.mock('./api', () => ({ api: { get: apiGet, post: apiPost }, errorMessage: (e: unknown) => String(e) }))
vi.mock('./App', () => ({ useUser: () => ({ role: 'admin' }) }))
vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
vi.mock('./worldmap', () => ({ WORLD_W: 100, WORLD_H: 100, WORLD_PATH: '' }))
vi.mock('./dates', () => ({ formatDateTime: (s: string) => s, formatDate: (s: string) => s }))
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig() as object), useNavigate: () => navigate,
}))

import TrackingPage from './pages/TrackingPage'

afterEach(() => { cleanup(); localStorage.clear(); apiGet.mockClear(); apiPost.mockClear(); navigate.mockClear() })

describe('TrackingPage — tooltip markera na dotyku', () => {
  it('tap markera przypina tooltip i NIE nawiguje; CTA nawiguje', async () => {
    localStorage.setItem('trackingMapMode', '2d')   // test dotyczy markerów SVG (mapa płaska)
    const { container } = render(<MemoryRouter><TrackingPage /></MemoryRouter>)

    const marker = await vi.waitFor(() => {
      const g = container.querySelector('g[role="button"]')
      if (!g) throw new Error('brak markera')
      return g as SVGGElement
    })

    fireEvent.click(marker)
    // tooltip przypięty i klikalny, nawigacja NIE odpalona tapem
    const tip = await vi.waitFor(() => {
      const el = container.querySelector('.map-tooltip.pinned')
      if (!el) throw new Error('brak przypiętego tooltipa')
      return el as HTMLElement
    })
    expect(tip.textContent).toContain('MSKU1')
    expect(navigate).not.toHaveBeenCalled()

    // CTA „Otwórz kontener" nawiguje
    fireEvent.click(screen.getByText(/trackOpenContainer/))
    expect(navigate).toHaveBeenCalledWith('/kontenery/42')
  })

  it('marker jest osiągalny z klawiatury (tabIndex + role=button)', async () => {
    localStorage.setItem('trackingMapMode', '2d')
    const { container } = render(<MemoryRouter><TrackingPage /></MemoryRouter>)
    const marker = await vi.waitFor(() => {
      const g = container.querySelector('g[role="button"]')
      if (!g) throw new Error('brak markera')
      return g as SVGGElement
    })
    expect(marker.getAttribute('tabindex')).toBe('0')
    fireEvent.keyDown(marker, { key: 'Enter' })
    await vi.waitFor(() => {
      if (!container.querySelector('.map-tooltip')) throw new Error('brak tooltipa')
    })
    expect(navigate).not.toHaveBeenCalled()
  })
})
