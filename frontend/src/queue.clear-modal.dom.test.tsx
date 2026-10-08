// @vitest-environment jsdom
// Czyszczenie kolejki z filtrem (data + statusy): klik otwiera modal z inputem daty
// i przyciskiem danger zamiast window.confirm.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const CONTAINER = {
  id: 7, container_no: 'MSDU0806613', company_id: 1, company_name: 'Acme',
  supplier_name: 'Dostawca A', vessel: 'MV DEMO ATLAS', eta: '2026-08-01', atd: null,
  notify_date: '2026-08-10', transport_type: 'kola', status: 'W_TRANSPORCIE',
  customs_status: 'BRAK', document_status: 'BRAK', purchasing_status: 'BRAK',
  order_numbers: 'PO-1', delivery_note: '', warehouse_name: 'DLT',
  incoming_delivery_no: '18001', purchase_note: '', forwarder_name: 'SPEDALFA',
  document_flow: '', sent_required: null, sent_number: '', sent_status: '',
  is_delayed: false, transport_id: null, order_number: null,
}

vi.mock('./api', () => ({
  api: {
    get: (path: string) => Promise.resolve(
      path.startsWith('/api/containers?') ? [CONTAINER]
        : path.startsWith('/api/containers/counts') ? {}
          : []),
    post: () => Promise.resolve(CONTAINER),
    put: () => Promise.resolve({}),
    patch: () => Promise.resolve(CONTAINER),
    del: () => Promise.resolve({ deleted: 1 }),
  },
  downloadFile: () => Promise.resolve(),
  ApiError: class extends Error {},
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => USER }))

globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

import QueuePage from './pages/QueuePage'

const mount = () => render(
  <MemoryRouter initialEntries={['/kolejka?spolka=acme']}><QueuePage /></MemoryRouter>)

beforeEach(() => localStorage.clear())
afterEach(cleanup)

describe('kolejka — modal czyszczenia z filtrem', () => {
  it('klik „Wyczyść kolejkę" otwiera modal z inputem daty i przyciskiem danger (bez window.confirm)', async () => {
    mount()
    await waitFor(() => expect(screen.getByText('MSDU0806613')).toBeTruthy())
    const confirmSpy = vi.spyOn(window, 'confirm')
    // „Wyczyść kolejkę" (destrukcyjne) siedzi w menu „⋯"
    fireEvent.click(document.querySelector('.kq-more-menu')!)
    fireEvent.click(screen.getByText(/Wyczyść kolejkę/))
    expect(confirmSpy).not.toHaveBeenCalled()
    const modal = document.querySelector('.modal')!
    expect(modal).toBeTruthy()
    expect(modal.querySelector('input[type="date"]')).toBeTruthy()
    await waitFor(() => expect(modal.querySelector('.btn.danger')).toBeTruthy())
  })
})
