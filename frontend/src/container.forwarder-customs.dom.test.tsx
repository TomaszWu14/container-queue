// @vitest-environment jsdom
// Decyzja 2026-09-28: odprawa = wyłącznie agencja celna. Spedytor na karcie kontenera nie widzi
// pozycji „Odprawa” (backend i tak maskuje status do BRAK) ani panelu zmiany statusu odprawy.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const { apiGet, role } = vi.hoisted(() => ({ apiGet: vi.fn(), role: { current: 'forwarder' } }))

vi.mock('./api', () => ({
  api: { get: apiGet, post: vi.fn(() => Promise.resolve([])), put: vi.fn(), patch: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: role.current }) }))
vi.mock('./i18n', async importOriginal => {
  const actual = await importOriginal<typeof import('./i18n')>()
  return { ...actual, useT: () => (key: string) => key }
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

afterEach(() => { cleanup(); apiGet.mockReset() })

const mount = async () => {
  apiGet.mockImplementation((url: string) => url === '/api/containers/1'
    ? Promise.resolve({ id: 1, container_no: 'CONT1', status: 'W_PORCIE', is_delayed: false,
        customs_status: 'BRAK' })
    : Promise.resolve([]))
  render(
    <MemoryRouter initialEntries={['/kontenery/1']}>
      <Routes><Route path="/kontenery/:id" element={<ContainerPage />} /></Routes>
    </MemoryRouter>,
  )
  await screen.findByText('CONT1')
}

describe('ContainerPage — spedytor bez odprawy', () => {
  it('spedytor: brak pozycji „Odprawa”', async () => {
    role.current = 'forwarder'
    await mount()
    expect(screen.queryAllByText('customs')).toHaveLength(0)
  })

  it('logistyka: pozycja „Odprawa” jest', async () => {
    role.current = 'logistics'
    await mount()
    expect(screen.queryAllByText('customs').length).toBeGreaterThan(0)
  })
})
