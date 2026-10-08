// @vitest-environment jsdom
// Kolejka: rozwijany panel szczegółów (także po F5) i komórki PO zwijane do licznika „› N” (2026-10-01).
// Testujemy zachowanie, nie wygląd.
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

// dwa różne dni i dwa różne magazyny — inaczej nie ma czego zwijać ani rozbijać
const CONTAINERS = [
  { ...base, id: 1, container_no: 'CSNU0110266', notify_date: '2026-08-10',
    warehouse_name: 'ACME', is_delayed: true, sent_number: '180022585',
    order_numbers: '4500617421\n4500617412\n4500617989' },
  { ...base, id: 2, container_no: 'TIIU9152821', notify_date: '2026-08-11',
    warehouse_name: 'DLT', sent_number: '180023076', order_numbers: '4500618818' },
]

vi.mock('./api', () => ({
  api: {
    get: (path: string) => Promise.resolve(
      path.startsWith('/api/containers?') ? CONTAINERS
        : path.startsWith('/api/containers/counts') ? {}
          : path.startsWith('/api/ui-config') ? { warehouse_eta_buffer_days: 3 }
            : []),
    post: () => Promise.resolve(CONTAINERS[0]),
    put: () => Promise.resolve({}),
    patch: () => Promise.resolve(CONTAINERS[0]),
  },
  downloadFile: () => Promise.resolve(),
  ApiError: class extends Error {},
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => USER }))

// jsdom nie zna ResizeObserver (kolejka mierzy nim wysokość paska narzędzi)
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

import QueuePage from './pages/QueuePage'

const mount = () => render(
  <MemoryRouter initialEntries={['/kolejka?spolka=acme']}><QueuePage /></MemoryRouter>)

const ready = () => waitFor(() => expect(screen.getByText('CSNU0110266')).toBeTruthy())

beforeEach(() => { localStorage.clear(); sessionStorage.clear() })
afterEach(cleanup)
// pełny render kolejki + szuflada — przy obciążonym runnerze domyślne limity bywają za małe

describe('kolejka — rozwijany panel szczegółów', () => {
  // „Pełna karta" w szufladzie to od 2026-09-30 osobny ekran (fullCard.dom.test.tsx); panel inline
  // zostaje dla podpowiedzi wyszukiwarki i przeżywa F5 (sessionStorage queue.expandedId)
  it('panel inline pokazuje sekcje, „Zwiń" go zamyka', async () => {
    sessionStorage.setItem('queue.expandedId', '1')
    mount()
    await waitFor(() => expect(document.querySelector('.cont-detail')).toBeTruthy())
    expect(screen.getByText('Droga kontenera')).toBeTruthy()
    expect(screen.getByText('Kontakt')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Zwiń' }))
    await waitFor(() => expect(document.querySelector('.cont-detail')).toBeNull())
  })
})

describe('kolejka 4a — PO i SENT zwinięte gdy jest ich więcej niż jeden', () => {
  it('pokazuje pierwszy numer i licznik wszystkich numerów, klik rozwija resztę', async () => {
    mount()
    await ready()
    expect(screen.getByText('4500617421')).toBeTruthy()
    expect(screen.queryByText('4500617412')).toBeNull()
    expect(screen.getByTitle('Pokaż wszystkie numery').textContent).toBe('3')
    fireEvent.click(screen.getByTitle('Pokaż wszystkie numery'))
    await waitFor(() => expect(screen.getByText('4500617989')).toBeTruthy())
    fireEvent.click(screen.getByTitle('Zwiń numery'))
    await waitFor(() => expect(screen.queryByText('4500617989')).toBeNull())
  })

  it('rozwijanie numerów nie zaznacza wiersza', async () => {
    mount()
    await ready()
    fireEvent.click(screen.getByTitle('Pokaż wszystkie numery'))
    await waitFor(() => expect(screen.getByText('4500617989')).toBeTruthy())
    expect(document.querySelector('.kq-row.selected')).toBeNull()
  })

  it('rozwinięty wiersz zostaje rozwinięty po przeładowaniu strony (T3, 2026-09-24)', async () => {
    sessionStorage.setItem('queue.expandedId', '1')   // jak po rozwinięciu z wyszukiwarki
    const first = mount()
    await waitFor(() => expect(screen.getByRole('region', { name: 'CSNU0110266' })).toBeTruthy())
    first.unmount()
    mount()   // bez ready(): numer jest wtedy i w wierszu, i w panelu
    await waitFor(() => expect(screen.getByRole('region', { name: 'CSNU0110266' })).toBeTruthy())
  })
})
