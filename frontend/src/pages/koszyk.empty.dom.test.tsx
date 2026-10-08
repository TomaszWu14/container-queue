// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import KoszykPage from './KoszykPage'

// C31 (audyt UI): puste konsolidacje zwinięte w „Puste konsolidacje (N)”, „Zamknij konsolidację”
// tylko przy wypełnieniu > 0, liczby po polsku (0,0 m³). Nic nie jest usuwane z danych.
vi.mock('../i18n', async (orig) => ({
  ...await orig<typeof import('../i18n')>(), useT: () => (k: string) => k,
}))
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({ api: { get: apiGet }, errorMessage: String }))

const CONTAINERS = [
  { id: 1, container_no: 'FULL0000001', consolidation_status: 'otwarty', capacity_cbm: 67.7,
    fill_cbm: 12.5, crd: null, order_count: 2 },
  { id: 2, container_no: 'EMPT0000002', consolidation_status: 'otwarty', capacity_cbm: 67.7,
    fill_cbm: 0, crd: null, order_count: 0 },
  { id: 3, container_no: 'EMPT0000003', consolidation_status: 'otwarty', capacity_cbm: 33.2,
    fill_cbm: 0, crd: null, order_count: 0 },
]
afterEach(() => { cleanup(); apiGet.mockReset() })

it('puste konsolidacje w zwiniętej sekcji, zamknięcie tylko przy wypełnieniu', async () => {
  apiGet.mockImplementation((url: string) =>
    Promise.resolve(url.startsWith('/api/consolidation/containers') ? CONTAINERS : []))
  render(<KoszykPage />)

  const full = (await screen.findByText('FULL0000001')).closest('tr')!
  expect(within(full).getByText('closeConsolidation')).toBeTruthy()
  expect(within(full).getByText('12,5 / 67,7 m³')).toBeTruthy()

  const section = screen.getByText('cartEmptyConsolidations').closest('details')!
  expect(section.open).toBe(false)
  // wiersze pustych są w danych (nic nie usunięte), ale bez przycisku zamknięcia
  const empty = within(section).getByText('EMPT0000002').closest('tr')!
  expect(within(empty).getByText('0,0 / 67,7 m³')).toBeTruthy()
  expect(within(section).queryByText('closeConsolidation')).toBeNull()
  expect(within(section).getByText('EMPT0000003')).toBeTruthy()
})
