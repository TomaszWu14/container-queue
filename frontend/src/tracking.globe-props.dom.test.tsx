// @vitest-environment jsdom
// Globus /sledzenie: tablice przekazywane do GlobeView to zależności efektu budującego scenę
// WebGL. Regresja: nowa tablica przy każdym renderze (klik statku, suwak replayu) =
// przebudowa renderera/tekstur/sceny co render. Rodzic musi podawać stabilne referencje.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const VESSEL = { id: 7, name: 'MV DEMO ATLAS', lat: 30, lon: 32, trail: [], delayed: 0,
  eta_alert: false, predicted_late: false, watched: [] }

const { apiGet, globeProps } = vi.hoisted(() => ({
  apiGet: vi.fn((url: string) => {
    if (url === '/api/tracking/map') return Promise.resolve(
      { points: [{ id: 1, container_no: 'MSKU1', lat: 1, lon: 2, status: 'w_drodze', location: '' }],
        unlocated: [], tracked: 1, total: 1 })
    if (url === '/api/tracking/vessels') return Promise.resolve([VESSEL])
    return Promise.resolve([])
  }),
  globeProps: [] as Array<Record<string, unknown>>,
}))

vi.mock('./api', () => ({
  api: { get: apiGet, post: vi.fn(() => Promise.resolve({})) },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: 'admin' }) }))
vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
vi.mock('./worldmap', () => ({ WORLD_W: 100, WORLD_H: 50, WORLD_PATH: '' }))
vi.mock('./pages/tracking/GlobeView', () => ({
  default: (p: Record<string, unknown>) => { globeProps.push(p); return <div data-testid="globe-stub" /> },
}))
vi.mock('./pages/tracking/VesselCard', () => ({ default: () => <div data-testid="vessel-card" /> }))
vi.mock('./pages/tracking/VesselsTable', () => ({ default: () => null }))

import TrackingPage from './pages/TrackingPage'

const last = () => globeProps[globeProps.length - 1]

afterEach(() => { cleanup(); localStorage.clear(); globeProps.length = 0 })

describe('TrackingPage → GlobeView: stabilne zależności sceny', () => {
  it('regresja: klik statku nie podaje nowych tablic (brak przebudowy WebGL)', async () => {
    const { findByTestId } = render(<MemoryRouter><TrackingPage /></MemoryRouter>)
    await findByTestId('globe-stub')
    await waitFor(() => expect((last().vessels as unknown[]).length).toBe(1))
    const before = last()
    act(() => { (before.onVesselClick as (v: unknown) => void)(VESSEL) })
    await findByTestId('vessel-card')
    const after = last()
    expect(after).not.toBe(before)                // rodzic przerenderował GlobeView
    expect(after.activeVesselId).toBe(7)
    for (const k of ['vessels', 'points', 'factories', 'routeWeather', 'containerPorts', 'statusColor'])
      expect(after[k], k).toBe(before[k])
  })
})
