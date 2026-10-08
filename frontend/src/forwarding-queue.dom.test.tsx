// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
vi.mock('./dates', () => ({ formatDate: (s: string) => s }))
vi.mock('./pages/QuoteRequestModal', () => ({ default: () => <div>MODAL</div> }))

const { apiGet, apiPatch } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPatch: vi.fn() }))
vi.mock('./api', () => ({ api: { get: apiGet, patch: apiPatch }, errorMessage: (e: unknown) => String(e) }))

import ForwardingRequestsPage from './pages/ForwardingRequestsPage'
afterEach(() => { cleanup(); apiGet.mockReset(); apiPatch.mockReset() })

const rows = [{ id: 1, container_no: 'MSDU1', warehouse_name: 'DLT', eta: '2026-07-08',
  notify_date: null, port_name: 'MUMBAI', needs_forwarding: false }]

// /api/forwarders zwraca listę spedytorów, /api/containers/to-forward — kolejkę
const getImpl = (path: string) =>
  Promise.resolve(path.includes('forwarders') ? [{ id: 9, name: 'SPEDALFA' }] : rows)

describe('ForwardingRequestsPage', () => {
  it('renderuje kolejkę i przełącza flagę', async () => {
    apiGet.mockImplementation(getImpl)
    apiPatch.mockResolvedValue({ ...rows[0], needs_forwarding: true })
    render(<MemoryRouter><ForwardingRequestsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('MSDU1')).toBeTruthy())
    fireEvent.click(screen.getByTitle('fwqFlagOn'))
    await waitFor(() => expect(apiPatch).toHaveBeenCalledWith(
      '/api/containers/1/needs-forwarding', { value: true }))
  })

  it('zaznaczenie + Utwórz zlecenie otwiera modal', async () => {
    apiGet.mockImplementation(getImpl)
    render(<MemoryRouter><ForwardingRequestsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('MSDU1')).toBeTruthy())
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText(/fwqCreate/))
    expect(screen.getByText('MODAL')).toBeTruthy()
  })
})
