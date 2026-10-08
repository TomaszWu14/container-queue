// @vitest-environment jsdom
// Filtry widoczne (decyzje 8, 14, 15, 17 z 2026-09-03-kolejka-ui-polish):
// klik w „opóźnione" ustawia filtr w query string, pasek chipów pojawia się
// przy aktywnym filtrze i „Wyczyść wszystkie" czyści query string.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const base = {
  company_id: 1, company_name: 'Acme', supplier_name: 'Dostawca A', vessel: 'MV DEMO ATLAS',
  eta: '2026-08-01', atd: null, transport_type: 'kola', status: 'W_TRANSPORCIE',
  customs_status: 'BRAK', document_status: 'BRAK', purchasing_status: 'BRAK',
  delivery_note: '', incoming_delivery_no: '18001', purchase_note: '',
  forwarder_name: 'SPEDALFA', document_flow: '', sent_required: null, sent_status: '',
  is_delayed: false, transport_id: null, order_number: null,
}

const CONTAINERS = [
  { ...base, id: 1, container_no: 'CSNU0110266', notify_date: '2026-08-10',
    warehouse_name: 'ACME', sent_number: '180022585', order_numbers: '4500617421' },
  { ...base, id: 2, container_no: 'TIIU9152821', notify_date: '2026-08-11',
    warehouse_name: 'ACME', sent_number: '180023076', order_numbers: '4500618818', is_delayed: true },
]

vi.mock('./api', () => ({
  api: {
    put: () => Promise.resolve({}),  // setPref → zapis profilu widoku (prefs.ts)
    get: (path: string) => Promise.resolve(
      path.startsWith('/api/containers?') ? CONTAINERS
        : path.startsWith('/api/containers/counts') ? {}
          : path.startsWith('/api/ui-config') ? { warehouse_eta_buffer_days: 3 }
            : []),
    post: () => Promise.resolve(CONTAINERS[0]),
    patch: () => Promise.resolve(CONTAINERS[0]),
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

const mount = (initial = '/kolejka?spolka=acme') => render(
  <MemoryRouter initialEntries={[initial]}><QueuePage /></MemoryRouter>)

const ready = () => waitFor(() => expect(screen.getByText('CSNU0110266')).toBeTruthy())

beforeEach(() => localStorage.clear())
afterEach(cleanup)

describe('kolejka — filtry widoczne', () => {
  it('pasek KPI usunięty — zakładka „Opóźnione" (z licznikiem) przełącza widok', async () => {
    mount()
    await ready()
    expect(document.querySelector('.kq-kpi')).toBeNull()
    expect(document.querySelector('.kq-crumbs')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /^Opóźnione/ }))
    await waitFor(() => expect(screen.getByRole('button', { pressed: true, name: /^Opóźnione/ })).toBeTruthy())
  })

  it('pasek chipów pojawia się przy aktywnym filtrze; × usuwa filtr, „Wyczyść wszystkie" czyści komplet (decyzja 15)', async () => {
    mount('/kolejka?spolka=acme&statek=EVER&opoznione=1')
    await ready()
    const bar = document.querySelector('.kq-filters')
    expect(bar).toBeTruthy()
    expect(bar!.textContent).toContain('EVER')

    const chipX = bar!.querySelector('.chip-x') as HTMLButtonElement
    fireEvent.click(chipX)
    await waitFor(() => expect(document.querySelector('.kq-filters')!.textContent).not.toContain('EVER'))

    const clearAll = screen.getByText('Wyczyść wszystkie')
    fireEvent.click(clearAll)
    await waitFor(() => expect(document.querySelector('.kq-filters .kq-chip')).toBeNull())
  })

  it('„+ Filtr → Transport": tryby jako pigułki z ikoną; klik ustawia chip, ponowny klik czyści', async () => {
    mount()
    await ready()
    fireEvent.click(document.querySelector('.kq-addfilter-btn')!)
    const group = screen.getByRole('group', { name: 'Transport' })
    expect(group.querySelectorAll('button .tr-badge svg').length).toBe(5)
    const rail = screen.getByRole('button', { name: 'kolej' })
    fireEvent.click(rail)
    await waitFor(() => expect(document.querySelector('.kq-filters')!.textContent).toContain('Transport: kolej'))
    expect(screen.getByRole('button', { name: 'kolej' }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: 'kolej' }))
    await waitFor(() => expect(document.querySelector('.kq-filters .kq-chip')).toBeNull())
  })

  it('stary przycisk „Wyczyść filtry" przy wyszukiwarce nie istnieje — zostaje tylko „Wyczyść wszystkie" (Task 4 unifikacja)', async () => {
    mount('/kolejka?spolka=acme&statek=EVER&opoznione=1')
    await ready()
    expect(screen.queryByText('Wyczyść filtry')).toBeNull()
    expect(screen.getByText('Wyczyść wszystkie')).toBeTruthy()
  })

  it('menu eksportu ma opcje „Bieżący widok" i „Cała kolejka" (decyzja 17)', async () => {
    mount()
    await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Eksport Excel' }))
    const menu = document.querySelector('.export-menu')!
    expect(menu.textContent).toContain('Bieżący widok')
    expect(menu.textContent).toContain('Cała kolejka')
  })
})
