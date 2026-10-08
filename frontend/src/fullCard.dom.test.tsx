// @vitest-environment jsdom
// „Pełna karta” z szuflady kolejki = osobny ekran /kontenery/:id (2026-09-30): bez elementów
// kolejki, nagłówek „czego to dotyczy”, ‹ › po kolejności z kolejki, „← Kolejka” wraca do
// tego samego widoku (query) na ten kontener; link bezpośredni — bez strzałek.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const base = {
  company_id: 1, company_name: 'Acme', supplier_name: 'Dostawca A', vessel: 'MV DEMO ATLAS',
  eta: '2026-08-01', atd: null, transport_type: 'kola', status: 'AWIZOWANY',
  customs_status: 'BRAK', document_status: 'BRAK', purchasing_status: 'BRAK',
  delivery_note: '', incoming_delivery_no: '18001', purchase_note: '',
  forwarder_name: 'SPEDALFA', document_flow: '', sent_required: null, sent_status: '',
  is_delayed: false, transport_id: null, order_number: null, updated_at: '2026-08-01T10:00:00',
}
const CONTAINERS = [
  { ...base, id: 1, container_no: 'CSNU0110266', notify_date: '2026-08-10', warehouse_name: 'ACME',
    is_delayed: true, order_numbers: '4500617421\n4500617412' },
  { ...base, id: 2, container_no: 'TIIU9152821', notify_date: '2026-08-11', warehouse_name: 'DLT',
    order_numbers: '4500618818' },
]

vi.mock('./api', () => ({
  api: {
    get: (path: string) => {
      const one = /^\/api\/containers\/(\d+)$/.exec(path)
      return Promise.resolve(
        one ? CONTAINERS.find(c => c.id === Number(one[1]))
          : path.startsWith('/api/containers?') ? CONTAINERS
            : path.startsWith('/api/containers/counts') ? {}
              : path.startsWith('/api/ui-config') ? { warehouse_eta_buffer_days: 3 }
                : path === '/api/watch' ? [1]
                  : path === '/api/watch/reasons' ? [{ container_id: 1, reason: 'reklamacja' }]
                    : [])
    },
    post: () => Promise.resolve({}),
    put: () => Promise.resolve({}),
    patch: () => Promise.resolve({}),
    upload: () => Promise.resolve({}),
  },
  downloadFile: () => Promise.resolve(),
  ApiError: class extends Error {},
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => USER }))
// panele pracy mają własne testy i swoje kształty odpowiedzi — tu liczy się układ ekranu
vi.mock('./collaboration', async orig => ({
  ...(await orig<typeof import('./collaboration')>()),
  DriverPanel: () => null, CustomsAgencyPanel: () => null, TransportOrdersPanel: () => null,
}))

globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

import QueuePage from './pages/QueuePage'
import ContainerPage from './pages/ContainerPage'

function Where() {
  const l = useLocation()
  return <output data-testid="where">{l.pathname + l.search}</output>
}
const mount = (entry: string) => render(
  <MemoryRouter initialEntries={[entry]}>
    <Routes>
      <Route path="/kolejka" element={<QueuePage />} />
      <Route path="/kontenery/:id" element={<ContainerPage />} />
    </Routes>
    <Where />
  </MemoryRouter>)
const where = () => screen.getByTestId('where').textContent

beforeEach(() => { localStorage.clear(); sessionStorage.clear() })
afterEach(cleanup)

describe('pełna karta z kolejki', () => {
  it('osobny ekran bez kolejki, nagłówek, ‹ › po kolejce i powrót do tego samego widoku', async () => {
    mount('/kolejka?spolka=acme')
    fireEvent.click(await screen.findByText('CSNU0110266'))
    fireEvent.click(await screen.findByRole('button', { name: 'Pełna karta' }))

    const h1 = await screen.findByRole('heading', { level: 1, name: 'CSNU0110266' })
    expect(where()).toBe('/kontenery/1')
    // nic z kolejki: zakładki widoków, tabela wierszy, szuflada, panel inline
    expect(screen.queryByRole('group', { name: 'Widoki kolejki' })).toBeNull()
    expect(document.querySelector('.kq-row, .kq-drawer, .cont-detail')).toBeNull()

    // nagłówek „czego to dotyczy”
    const head = h1.closest('header')!
    expect(within(head).getByText('Opóźniony', { exact: false })).toBeTruthy()
    expect(within(head).getByText('reklamacja')).toBeTruthy()   // powód obserwacji
    expect(head.textContent).toContain('Dostawca A · MV DEMO ATLAS · PO')
    // wszystkie PO, nie tylko pierwszy: licznik + pierwszy numer (2026-10-01)
    expect(head.querySelector('.multi-more')?.textContent).toBe('2')
    expect(head.querySelector('.multi-values')?.textContent).toContain('4500617421')
    expect(head.textContent).toMatch(/Acme · ACME · Dostawa: 10 sierpnia 2026, poniedziałek/)
    expect(head.querySelectorAll('.kq-dr-stages i')).toHaveLength(10)
    expect(head.textContent).toMatch(/Etap \d+ z 10/)

    // zakładki jak w szufladzie
    const tabs = screen.getAllByRole('tab').map(b => b.textContent?.replace(/\s*[\d…]+$/, ''))
    expect(tabs).toEqual(['Szczegóły', 'Dokumenty', 'Wiadomości', 'Koszty', 'Historia'])

    // ‹ › po kolejności z kolejki
    expect((screen.getByRole('button', { name: 'Poprzedni kontener' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Następny kontener' }))
    await screen.findByRole('heading', { level: 1, name: 'TIIU9152821' })
    expect(where()).toBe('/kontenery/2')

    // „← Kolejka” = ten sam widok (query) z otwartym kontenerem, z którego wracamy
    fireEvent.click(screen.getByRole('button', { name: 'Kolejka' }))
    await waitFor(() => expect(where()).toBe('/kolejka?spolka=acme&kontener=2'))
    await waitFor(() => expect(document.querySelector('.kq-row.active')?.textContent).toContain('TIIU9152821'))
  })

  it('link bezpośredni: karta bez strzałek ‹ ›, „Kolejka” prowadzi do kolejki', async () => {
    mount('/kontenery/1')
    await screen.findByRole('heading', { level: 1, name: 'CSNU0110266' })
    expect(screen.queryByRole('button', { name: 'Następny kontener' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Poprzedni kontener' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Kolejka' }))
    await waitFor(() => expect(where()).toBe('/kolejka'))
  })
})
