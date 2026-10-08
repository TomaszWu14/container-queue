// @vitest-environment jsdom
// Strażnik kolumny „Wypełnienie" (batch /containers/fill-summary) i ikony ⚠ kolizji
// transportowej (/containers/transport-conflicts) w wierszach kolejki.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const base = {
  company_id: 1, company_name: 'Acme', supplier_name: 'Dostawca A',
  vessel: 'MV DEMO ATLAS', eta: '2026-08-01', atd: null, notify_date: '2026-08-10',
  transport_type: 'kola', status: 'W_TRANSPORCIE', customs_status: 'BRAK',
  document_status: 'BRAK', purchasing_status: 'BRAK', order_numbers: '',
  delivery_note: '', incoming_delivery_no: '', purchase_note: '',
  forwarder_name: 'SPEDALFA', document_flow: '', sent_required: null, sent_number: '',
  sent_status: '', is_delayed: false, transport_id: null, order_number: null,
}
const CONTAINERS = [
  { ...base, id: 1, container_no: 'MSDU0806613', warehouse_name: 'DLT' },
  { ...base, id: 2, container_no: 'TCLU1234568', warehouse_name: 'ACME' },
]

const fillCalls: string[] = []

vi.mock('./api', () => ({
  api: {
    get: (path: string) => {
      if (path.startsWith('/api/containers/fill-summary')) {
        fillCalls.push(path)
        return Promise.resolve({ 1: 87.5, 2: null })
      }
      if (path.startsWith('/api/containers/transport-conflicts')) {
        return Promise.resolve({ conflicts: [
          { container_id: 1, job_number: 'TJ-1', day: '2026-08-10',
            warehouses: ['DLT', 'ACME'] },
        ] })
      }
      return Promise.resolve(
        path.startsWith('/api/containers?') ? CONTAINERS
          : path.startsWith('/api/containers/counts') ? {} : [])
    },
    post: () => Promise.resolve({}),
    put: () => Promise.resolve({}),
    patch: () => Promise.resolve({}),
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

beforeEach(() => { localStorage.clear(); fillCalls.length = 0 })
afterEach(cleanup)

describe('kolejka — kolumna % wypełnienia + kolizje transportowe', () => {
  it('pokazuje % z batcha (jedno żądanie), a brak danych jako kreskę', async () => {
    const { container } = mount()
    await waitFor(() => expect(screen.getByText('MSDU0806613')).toBeTruthy())
    await waitFor(() => expect(container.querySelector('.kq-fill')).toBeTruthy())
    const bars = [...container.querySelectorAll('.kq-fill')]
    expect(bars.some(b => b.textContent?.includes('88%'))).toBe(true)   // id 1: 87.5 → 88%
    // id 2: null → kreska (żaden pasek nie pokazuje % dla TCLU…)
    expect(bars.length).toBe(1)
    // batch: jedno żądanie fill-summary z oboma id, nie N × /packing
    expect(fillCalls.length).toBe(1)
    expect(fillCalls[0]).toContain('ids=1,2')
  })

  it('kontener w kolizji transportowej dostaje ikonę ⚠ z magazynami w tooltipie', async () => {
    const { container } = mount()
    await waitFor(() => expect(screen.getByText('MSDU0806613')).toBeTruthy())
    await waitFor(() => expect(container.querySelector('.conflict-warn')).toBeTruthy())
    const warns = [...container.querySelectorAll('.conflict-warn')]
    expect(warns.length).toBe(1)   // tylko kontener 1
    expect(warns[0].getAttribute('title')).toContain('DLT / ACME')
  })
})
