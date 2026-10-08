// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Vessel, VesselCargo } from './types'

const cargo: VesselCargo = {
  items_visible: true,
  containers: [{
    id: 7, container_no: 'TGBU6784203', company: 'ACME', status: 'W_TRANSPORCIE',
    eta: '2026-10-01', is_special: false,
    items: [{ material: 'REF001', description: 'Rękawice', quantity: '500', unit: 'SZT' }],
  }],
}

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn((url: string) => Promise.resolve(
    url.endsWith('/watchers') ? { watching: false, watchers: [] } : cargo)),
  apiPost: vi.fn(() => Promise.resolve({ is_special: true })),
}))
vi.mock('../../api', () => ({
  api: { get: apiGet, post: apiPost, upload: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../dates', () => ({ formatDateTime: (s: string) => s, formatDate: (s: string) => s }))

import VesselCard from './VesselCard'

const vessel: Vessel = {
  id: 3, name: 'MV TESTOWA', mmsi: 111222330, imo: 9000003,
  lat: 35.12, lon: 18.4, sog: 17.3, cog: 42, destination: 'PL GDN',
  ais_eta: '2026-10-02T06:00:00', last_seen: '2026-09-18T10:00:00',
  trail: [], companies: ['ACME'], containers: 2, delayed: 0,
  drift_days: null, eta_alert: false, hours_to_dest: null, near_port: '',
  predicted_late: false, length_m: 366, beam_m: 51, has_photo: false,
}

afterEach(() => { cleanup(); vi.clearAllMocks() })

const renderCard = (over: Partial<Parameters<typeof VesselCard>[0]> = {}) =>
  render(<VesselCard vessel={vessel} companyColor={{}} canEdit isAdmin={false}
                     onClose={() => {}} onOpenContainer={() => {}} {...over} />)

describe('VesselCard', () => {
  it('renderuje parametry statku (IMO, MMSI, wymiary, prędkość, cel)', () => {
    renderCard()
    expect(screen.getByText('9000003')).toBeTruthy()
    expect(screen.getByText('111222330')).toBeTruthy()
    expect(screen.getByText('366 × 51 m')).toBeTruthy()
    expect(screen.getByText(/17\.3 kn/)).toBeTruthy()
    expect(screen.getByText('PL GDN')).toBeTruthy()
    // placeholder SVG zamiast zdjęcia
    expect(document.querySelector('.vessel-photo.placeholder')).toBeTruthy()
  })

  it('rozwija listę kontenerów i akordeon zawartości', async () => {
    renderCard()
    fireEvent.click(screen.getByText(/contAbbrev/))
    await waitFor(() => expect(screen.getByText('TGBU6784203')).toBeTruthy())
    expect(apiGet).toHaveBeenCalledWith('/api/tracking/vessels/3/cargo')
    fireEvent.click(screen.getByText(/vcContents/))
    expect(screen.getByText('REF001')).toBeTruthy()
    expect(screen.getByText('Rękawice')).toBeTruthy()
    expect(screen.getByText(/500 SZT/)).toBeTruthy()
  })

  it('flaguje kontener jako specjalny (🚩)', async () => {
    renderCard()
    fireEvent.click(screen.getByText(/contAbbrev/))
    await waitFor(() => expect(screen.getByText('TGBU6784203')).toBeTruthy())
    fireEvent.click(screen.getByTitle('specialToggle'))
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('/api/containers/7/special', { is_special: true }))
  })

  it('bez canEdit nie pokazuje przycisku flagi', async () => {
    renderCard({ canEdit: false })
    fireEvent.click(screen.getByText(/contAbbrev/))
    await waitFor(() => expect(screen.getByText('TGBU6784203')).toBeTruthy())
    expect(screen.queryByTitle('specialToggle')).toBeNull()
  })

  it('lista MOICH obserwowanych kontenerów na pokładzie z powodem', () => {
    renderCard({ vessel: { ...vessel, watched: [{ id: 7, container_no: 'TGBU6784203', reason: 'Reklamacja' }] } })
    expect(screen.getByText('watchedAboard')).toBeTruthy()
    expect(screen.getByText('Reklamacja')).toBeTruthy()
  })
})
