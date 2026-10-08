// @vitest-environment jsdom
// Karta kontenera — nagłówek (audyt UI A26/A27/A28/C34 — UX-015, UX-016, UX-017, UX-039):
// - na wierzchu tylko główne akcje (Zmień status, Edytuj); CMR, karta rozładunku, link i „Specjalny”
//   w menu „Więcej” (dawniej 7 równorzędnych przycisków w 3 rzędach na telefonie),
// - kluczowe pola (status, ETA, awizacja, magazyn, dostawca) na początku, puste pola zwinięte za
//   „Pokaż puste pola (N)” — kreski „—” nie dominują siatki,
// - na telefonie siatka pól w 2 kolumnach.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { readAppCss } from './appCss.testutil'

const { apiGet, role } = vi.hoisted(() => ({ apiGet: vi.fn(), role: { current: 'admin' } }))
vi.mock('./api', () => ({
  api: { get: apiGet, post: vi.fn(() => Promise.resolve([])), put: vi.fn(), patch: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: role.current }) }))
vi.mock('./components', () => ({
  ContainerFormModal: () => null, CustomsBadge: () => 'CB', DocumentBadge: () => 'DB',
  PurchasingBadge: () => 'PB', StatusBadge: () => 'SB', StatusModal: () => null,
  useDicts: () => ({}),
}))
vi.mock('./collaboration', () => ({
  AttachmentsPanel: () => null, CustomsAgencyPanel: () => null,
  DriverPanel: () => null, MessagesPanel: () => null, TransportOrdersPanel: () => null,
}))
vi.mock('./pages/ContainerItems', () => ({ ItemsPanel: () => null, SentLinksPanel: () => null }))
vi.mock('./pages/ComplaintsPanel', () => ({ ComplaintsPanel: () => null }))

import ContainerPage from './pages/ContainerPage'

afterEach(() => { cleanup(); apiGet.mockReset(); role.current = 'admin' })

function mount() {
  apiGet.mockImplementation((url: string) => url === '/api/containers/1'
    ? Promise.resolve({ id: 1, container_no: 'CONT1', status: 'W_PORCIE', is_delayed: false,
        customs_status: 'BRAK', eta: '2026-08-14', notify_date: '2026-08-19', warehouse_name: 'ACME',
        supplier_name: 'Dostawca', company_name: 'Iberia', vessel: 'MAERSK', documents_ok: false })
    : Promise.resolve([]))
  render(
    <MemoryRouter initialEntries={['/kontenery/1']}>
      <Routes><Route path="/kontenery/:id" element={<ContainerPage />} /></Routes>
    </MemoryRouter>,
  )
}

describe('karta kontenera — nagłówek', () => {
  it('główne akcje na wierzchu, reszta w menu „Więcej”', async () => {
    mount()
    await screen.findByText('CONT1')
    const head = document.querySelector('.ct-head-actions')!
    // przyciski z tekstem (ikona wiedzy 📘 ma tylko aria-label)
    const visible = [...head.querySelectorAll(':scope > button')].map(b => b.textContent?.trim()).filter(Boolean)
    expect(visible).toEqual(['Zmień status', 'Edytuj'])
    expect(screen.queryByText('List CMR')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Więcej/ }))
    const items = screen.getAllByRole('menuitem').map(i => i.textContent?.trim())
    expect(items).toEqual(['Specjalny', 'List CMR', 'Karta rozładunku'])
  })

  it('agencja celna nie ma „Karty rozładunku” jako pierwszego przycisku (C34)', async () => {
    role.current = 'customs'
    mount()
    await screen.findByText('CONT1')
    const head = document.querySelector('.ct-head-actions')!
    expect([...head.querySelectorAll(':scope > button')].map(b => b.textContent?.trim())).not.toContain('Karta rozładunku')
  })

  it('kluczowe pola pierwsze, puste zwinięte za „Pokaż puste pola (N)”', async () => {
    mount()
    await screen.findByText('CONT1')
    const labels = () => [...document.querySelectorAll('.detail-grid .item > b')].map(b => b.textContent)
    expect(labels().slice(0, 5)).toEqual(['Status', 'ETA', 'Awizacja', 'Magazyn', 'Dostawca'])
    expect([...document.querySelectorAll('.detail-grid .item')].some(i => i.textContent?.endsWith('—'))).toBe(false)
    const toggle = screen.getByRole('button', { name: /Pokaż puste pola \(\d+\)/ })
    const before = labels().length
    fireEvent.click(toggle)
    expect(labels().length).toBeGreaterThan(before)
    expect(screen.getByRole('button', { name: 'Ukryj puste pola' })).toBeTruthy()
    expect(readAppCss()).toMatch(/@media \(max-width: 640px\) \{[^}]*\.detail-grid \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/)
  })
})
