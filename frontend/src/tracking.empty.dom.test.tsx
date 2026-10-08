// @vitest-environment jsdom
// UX-038 / audyt UI C30: /sledzenie bez danych = pusty stan z komunikatem i akcją zamiast
// pełnego globusa; legenda etapów bez zdublowanych numerów, warstwy i legenda w jednej kolumnie.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiGet } = vi.hoisted(() => ({
  apiGet: vi.fn((url: string) => {
    if (url === '/api/tracking/map') return Promise.resolve(
      { points: [], unlocated: [], tracked: 0, total: 0 })
    return Promise.resolve([])
  }),
}))

vi.mock('./api', () => ({
  api: { get: apiGet, post: vi.fn(() => Promise.resolve({})) },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: 'forwarder' }) }))
vi.mock('./worldmap', () => ({ WORLD_W: 100, WORLD_H: 50, WORLD_PATH: '' }))

import TrackingPage from './pages/TrackingPage'
import { StatusLegend } from './pages/tracking/TrackingPanels'

afterEach(() => { cleanup(); localStorage.clear(); apiGet.mockClear() })

describe('Śledzenie — pusty stan (C30)', () => {
  it('brak kontenerów i statków → komunikat + akcja, bez mapy; akcja rozwija mapę', async () => {
    localStorage.setItem('trackingMapMode', '2d')
    const { container } = render(<MemoryRouter><TrackingPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('Brak kontenerów kwalifikujących się do śledzenia.')).toBeTruthy())
    expect(container.querySelector('.empty-state')).toBeTruthy()
    expect(container.querySelector('.map-wrap')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Pokaż mapę/ }))
    expect(container.querySelector('.map-wrap')).toBeTruthy()
    // warstwy i legenda w jednej kolumnie — legenda nie może przykryć warstw
    const side = container.querySelector('.map-side')!
    expect(side.querySelector('.map-layers')).toBeTruthy()
    expect(side.querySelector('details.map-legend-glass')).toBeTruthy()
  })
})

describe('Śledzenie — legenda etapów (C30)', () => {
  it('bez numerów etapu — żadnych duplikatów „4 ·"/„9 ·"', () => {
    const { container } = render(<StatusLegend data={null} />)
    const labels = [...container.querySelectorAll('.map-legend > .row')].map(el => el.textContent!.trim())
    expect(labels).toContain('Transport morski')
    expect(labels).toContain('Port docelowy')
    expect(labels.some(l => /^\d/.test(l))).toBe(false)
    expect(new Set(labels).size).toBe(labels.length)
  })
})
