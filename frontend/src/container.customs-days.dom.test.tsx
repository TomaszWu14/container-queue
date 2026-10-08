// @vitest-environment jsdom
// Licznik „otwarta od N dni” odprawy: customs_assigned_at to NAIWNY UTC z backendu.
// Strefa +9 (bez DST) — w strefie UTC (CI) błąd lokalnego parsowania byłby niewidoczny.
process.env.TZ = 'Asia/Tokyo'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('./api', () => ({
  api: { get: apiGet, post: vi.fn(() => Promise.resolve([])), put: vi.fn(), patch: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: 'admin' }) }))
vi.mock('./i18n', async importOriginal => {
  const actual = await importOriginal<typeof import('./i18n')>()
  return { ...actual, useT: () => (key: string) => key === 'customsDaysOpen' ? 'otwarta {n} dni' : key }
})
vi.mock('./components', () => ({
  ContainerFormModal: () => null, CustomsBadge: () => null, DocumentBadge: () => null,
  PurchasingBadge: () => null, StatusBadge: () => null, StatusModal: () => null,
  useDicts: () => ({}),
}))
vi.mock('./collaboration', () => ({
  AttachmentsPanel: () => null, CustomsAgencyPanel: () => null,
  DriverPanel: () => null, MessagesPanel: () => null, TransportOrdersPanel: () => null,
}))
vi.mock('./pages/ContainerItems', () => ({ ItemsPanel: () => null, SentLinksPanel: () => null }))
vi.mock('./pages/ComplaintsPanel', () => ({ ComplaintsPanel: () => null }))

import ContainerPage from './pages/ContainerPage'

afterEach(() => { cleanup(); apiGet.mockReset(); vi.restoreAllMocks() })

describe('ContainerPage — licznik dni otwartej odprawy', () => {
  it('liczy od chwili w UTC, nie od naiwnego stringa w czasie lokalnym', async () => {
    expect(new Date(2026, 0, 1).getTimezoneOffset()).toBe(-540)   // strefa faktycznie +9
    // zlecona 21.09 00:00 UTC, teraz 21.09 22:00 UTC → 22 h → 0 pełnych dni
    vi.spyOn(Date, 'now').mockReturnValue(Date.UTC(2026, 8, 21, 22, 0))
    apiGet.mockImplementation((url: string) => url === '/api/containers/1'
      ? Promise.resolve({ id: 1, container_no: 'CONT1', status: 'W_PORCIE', is_delayed: false,
          customs_status: 'ZLECONA', customs_assigned_at: '2026-09-21T00:00:00' })
      : Promise.resolve([]))
    render(
      <MemoryRouter initialEntries={['/kontenery/1']}>
        <Routes><Route path="/kontenery/:id" element={<ContainerPage />} /></Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByText('otwarta 0 dni')).toBeTruthy()
  })
})

describe('ContainerPage — agencja celna w nagłówku (A25)', () => {
  const mount = (extra: object) => {
    apiGet.mockImplementation((url: string) => url === '/api/containers/2'
      ? Promise.resolve({ id: 2, container_no: 'CONT2', status: 'W_PORCIE', is_delayed: false,
          customs_status: 'ZLECONA', customs_agency: '', ...extra })
      : Promise.resolve([]))
    render(
      <MemoryRouter initialEntries={['/kontenery/2']}>
        <Routes><Route path="/kontenery/:id" element={<ContainerPage />} /></Routes>
      </MemoryRouter>,
    )
  }
  it('pokazuje agencję ze słownika, nie pusty wolny tekst', async () => {
    mount({ customs_agency_id: 3, customs_agency_name: 'Agencja Łódź' })
    expect(await screen.findByText('Agencja Łódź')).toBeTruthy()
  })
  it('stare dane bez słownika: fallback na wolny tekst', async () => {
    mount({ customs_agency: 'Stara Agencja', customs_agency_id: null, customs_agency_name: null })
    expect(await screen.findByText('Stara Agencja')).toBeTruthy()
  })
})
