// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { Container } from './types'

const baseContainer = {
  id: 1, container_no: 'CONT1', is_delayed: false,
} as unknown as Container

const { apiGet } = vi.hoisted(() => ({
  apiGet: vi.fn((url: string) => {
    if (url.endsWith('/history')) return Promise.resolve([])
    if (url.endsWith('/events')) return Promise.resolve([])
    if (url.endsWith('/timeline')) return Promise.resolve([])
    return Promise.resolve(currentContainer)
  }),
}))

let currentContainer: Container = baseContainer

vi.mock('./api', () => ({
  api: { get: apiGet, post: vi.fn(() => Promise.resolve([])), put: vi.fn(), patch: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: 'admin' }) }))
vi.mock('./i18n', async importOriginal => {
  const actual = await importOriginal<typeof import('./i18n')>()
  return {
    ...actual,
    useT: () => (key: string) => ({
      transitCustomer: 'Klient docelowy',
      customerName: 'Nazwa',
      customerAddress: 'Adres dostawy',
      customerContact: 'Kontakt',
      edit: 'Edytuj',
    } as Record<string, string>)[key] ?? key,
  }
})
vi.mock('./dates', () => ({ formatDateTime: (s: string) => s, relTime: () => 'nigdy',
                            formatNum: (n: number) => String(n) }))   // lazy panel 3D
vi.mock('./components', () => ({
  ContainerFormModal: () => null,
  CustomsBadge: () => null,
  DocumentBadge: () => null,
  PurchasingBadge: () => null,
  StatusBadge: () => null,
  StatusModal: () => null,
  useDicts: () => ({}),
}))
vi.mock('./collaboration', () => ({
  AttachmentsPanel: () => null,
  CustomsAgencyPanel: () => null,
 
  DriverPanel: () => null,
  MessagesPanel: () => null,
  TransportOrdersPanel: () => null,
}))
vi.mock('./pages/ContainerItems', () => ({
  ItemsPanel: () => null,
  SentLinksPanel: () => null,
}))
vi.mock('./pages/ComplaintsPanel', () => ({ ComplaintsPanel: () => null }))

import ContainerPage from './pages/ContainerPage'

afterEach(() => { cleanup(); apiGet.mockClear() })

const renderPage = () => render(
  <MemoryRouter initialEntries={['/kontenery/1']}>
    <Routes><Route path="/kontenery/:id" element={<ContainerPage />} /></Routes>
  </MemoryRouter>,
)

describe('ContainerPage — sekcja klienta docelowego', () => {
  it('kontener tranzytowy: pokazuje nagłówek i dane klienta', async () => {
    currentContainer = { ...baseContainer, is_transit: true, customer_name: 'ACME',
      customer_address: 'ul. Testowa 1', customer_contact: '+48 111 222 333' } as unknown as Container
    renderPage()
    expect(await screen.findByText('Klient docelowy')).toBeTruthy()
    expect(screen.getByText('ACME')).toBeTruthy()
  })

  it('pole Transport: znacznik z ikoną w rozmiarze karty (20px)', async () => {
    currentContainer = { ...baseContainer, transport_type: 'kolej' } as unknown as Container
    renderPage()
    const badge = await screen.findByRole('img', { name: 'transport_kolej' })
    expect(badge.classList.contains('tr-badge--kolej')).toBe(true)
    expect(badge.querySelector('svg')!.getAttribute('width')).toBe('20')
  })

  it('kontener nietranzytowy: sekcji nie ma', async () => {
    currentContainer = { ...baseContainer, is_transit: false, customer_name: 'ACME',
      customer_address: '', customer_contact: '' } as unknown as Container
    renderPage()
    await screen.findByText('CONT1')
    expect(screen.queryByText('Klient docelowy')).toBeNull()
  })
})
