// @vitest-environment jsdom
// K3 regresja: VesselMiniMap dzieli trasę przez antymerydian na osobne polyline
// (jedna ciągła rysowałaby fałszywą kreskę w poprzek mapy).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiGet } = vi.hoisted(() => ({
  apiGet: vi.fn(() => Promise.resolve([{
    id: 1, name: 'MV DEMO ATLAS', lat: 12, lon: -170, cog: 90, sog: 10,
    trail: [[10, 170], [11, 179], [12, -179]],
    companies: [], containers: 0, delayed: 0, eta_alert: false,
    predicted_late: false, near_port: null, destination: null,
    ais_eta: null, last_seen: null, hours_to_dest: null, drift_days: 0,
  }])),
}))

vi.mock('./api', () => ({ api: { get: apiGet }, errorMessage: (e: unknown) => String(e) }))
vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
vi.mock('./worldmap', () => ({ WORLD_W: 360, WORLD_H: 180, WORLD_PATH: '' }))

import VesselMiniMap from './pages/tracking/VesselMiniMap'

afterEach(() => { cleanup(); apiGet.mockClear() })

describe('K3 — VesselMiniMap trasa przez antymerydian', () => {
  it('trail 179 → -179 renderuje dwa segmenty polyline', async () => {
    const { container } = render(<MemoryRouter><VesselMiniMap vesselName="MV DEMO ATLAS" /></MemoryRouter>)
    await waitFor(() => expect(container.querySelectorAll('polyline').length).toBe(2))
    for (const pl of container.querySelectorAll('polyline')) {
      // żaden segment nie rozciąga się przez całą szerokość mapy
      const xs = (pl.getAttribute('points') ?? '').split(' ').map(p => Number(p.split(',')[0]))
      expect(Math.max(...xs) - Math.min(...xs)).toBeLessThan(180)
    }
  })
})
