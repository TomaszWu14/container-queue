// @vitest-environment jsdom
// W8 regresja: awaria fetchu /api/tracking/vessels nie może zniknąć w ciszy —
// user musi zobaczyć komunikat na mapie.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn((url: string) => {
    if (url === '/api/tracking/vessels') return Promise.reject(new Error('fail'))
    if (url === '/api/tracking/map') return Promise.resolve(
      { points: [], unlocated: [], tracked: 0, total: 0 })
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
vi.mock('./worldmap', () => ({ WORLD_W: 100, WORLD_H: 100, WORLD_PATH: '' }))
vi.mock('./dates', () => ({ formatDateTime: (s: string) => s, formatDate: (s: string) => s }))

import TrackingPage from './pages/TrackingPage'

afterEach(() => { cleanup(); apiGet.mockClear(); apiPost.mockClear() })

describe('W8 — TrackingPage komunikat awarii warstwy AIS', () => {
  it('pokazuje komunikat gdy /api/tracking/vessels odrzuca', async () => {
    render(<MemoryRouter><TrackingPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('aisLayerError')).toBeTruthy())
  })
})
