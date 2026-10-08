// @vitest-environment jsdom
// Kolejka Enterprise: zakładki widoków z licznikami (bez KPI/H1), nagłówek grupy dnia w jednej
// linii z limitami magazynów (nadpisanie per-datę z /api/limits wygrywa z default_daily_limit),
// podgrupy planowania, grupowanie, zwijanie grup i sortowanie po nagłówku.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  { ...base, id: 1, container_no: 'MSDU0806613', warehouse_name: 'DLT', is_delayed: true },
  { ...base, id: 2, container_no: 'TCLU1234568', warehouse_name: 'DLT', customs_status: 'ZLECONA' },
  { ...base, id: 3, container_no: 'HLXU7654324', warehouse_name: 'DLT', demurrage_deadline: '2000-01-01' },
  { ...base, id: 4, container_no: 'CAIU4811390', warehouse_name: 'ACME', notify_date: '2026-08-11' },
]
let data: Record<string, unknown>[] = CONTAINERS
const WAREHOUSES = [
  { id: 1, name: 'DLT', company_id: 1, country: 'PL', default_daily_limit: 2, is_active: true },
  { id: 2, name: 'ACME', company_id: 1, country: 'PL', default_daily_limit: 7, is_active: true },
]

vi.mock('./api', () => ({
  api: {
    get: (path: string) => Promise.resolve(
      path.startsWith('/api/containers?') ? data
        : path.startsWith('/api/containers/counts') ? {}
          : path.startsWith('/api/warehouses') ? WAREHOUSES
            // wyjątek kalendarza: DLT ma tego dnia limit 4 (zamiast domyślnych 2)
            : path.startsWith('/api/limits?warehouse_id=1')
              ? [{ warehouse_id: 1, day: '2026-08-10', limit: 4 }]
              : []),
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

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); data = CONTAINERS })
afterEach(cleanup)

const mount = () => render(
  <MemoryRouter initialEntries={['/kolejka?spolka=acme']}><QueuePage /></MemoryRouter>)
const ready = () => waitFor(() => expect(screen.getByText('MSDU0806613')).toBeTruthy())
const rowNos = () => [...document.querySelectorAll('.kq-row .kq-no b')].map(e => e.textContent)

describe('Kolejka Enterprise', () => {
  it('bez nagłówka strony i paska KPI — liczniki w zakładkach widoków', async () => {
    mount()
    await ready()
    expect(document.querySelector('.kq-kpi, .kq-crumbs, h1:not(.sr-only)')).toBeNull()
    const tabs = within(screen.getByRole('group', { name: 'Widoki kolejki' })).getAllByRole('button').map(tb => tb.textContent)
    expect(tabs.slice(0, 4)).toEqual(['Wszystkie 4', 'Opóźnione 1', 'Demurrage ≤ 2 dni 1', 'Odprawa otwarta 1'])
    fireEvent.click(screen.getByRole('button', { name: /Odprawa otwarta/ }))
    await waitFor(() => expect(rowNos()).toEqual(['TCLU1234568']))
  })

  it('nagłówek dnia w jednej linii: liczba kont., limit magazynu z nadpisania (DLT 3/4), Σ, bez chipa opóźnień', async () => {
    const { container } = mount()
    await ready()
    await waitFor(() => {
      const chips = [...container.querySelectorAll('.kq-gchip')].map(c => c.textContent)
      expect(chips).toContain('DLT 3/4')
    })
    const head = container.querySelector('.kq-ghead')!
    expect(head.textContent).toContain('3 kont.')
    expect(head.textContent).not.toContain('opóźn.')
    const dlt = [...head.querySelectorAll('.kq-gchip')].find(c => c.textContent === 'DLT 3/4')!
    expect(dlt.className).not.toContain('warn')   // 3 z 4 — bez przekroczenia
    // suma narastająca tygodnia (pon 10.08: 3, wt 11.08: 3+1)
    const sums = [...container.querySelectorAll('.kq-ghead')].map(h => h.textContent?.match(/Σ \d+/)?.[0])
    expect(sums).toEqual(['Σ 3', 'Σ 4'])
    // ● opóźnienia przy numerze kontenera
    expect(screen.getByText('MSDU0806613').closest('.kq-no')!.querySelector('.kq-late-dot')).toBeTruthy()
  })

  it('jedna podgrupa planowania: tylko licznik w nagłówku grupy (bez osobnego wiersza), nadal zwija', async () => {
    const { container } = mount()
    await ready()
    expect(container.querySelector('.kq-plan')).toBeNull()
    const plan = container.querySelector('.kq-ghead .kq-gplan') as HTMLButtonElement
    expect(plan.textContent).toContain('Propozycje')
    expect(plan.textContent).toContain('(3)')
    fireEvent.click(plan)
    await waitFor(() => expect(screen.queryByText('MSDU0806613')).toBeNull())
    expect(localStorage.getItem('queueCollapsedPlanning')).toContain('PROPOZYCJA')
  })

  it('2–3 podgrupy planowania: cienkie separatory między wierszami, bez licznika w nagłówku', async () => {
    data = CONTAINERS.map((c, i) => ({ ...c, notify_date: '2026-08-10',
      planning_status: ['POTWIERDZONE', 'WYSLANE', 'WYSLANE', 'PROPOZYCJA'][i] }))
    const { container } = mount()
    await ready()
    const seps = [...container.querySelectorAll('.kq-plan .kq-plan-btn')].map(b => b.textContent)
    expect(seps).toHaveLength(3)
    expect(seps[1]).toMatch(/\(2\)$/)
    expect(container.querySelector('.kq-ghead .kq-gplan')).toBeNull()
  })

  it('grupuj=Etap: bez kolumny Status; Dzień: Status zwykłym tekstem; odprawa „Brak" jako „—"', async () => {
    mount()
    await ready()
    const row = screen.getByText('MSDU0806613').closest('tr')!
    expect(row.querySelector('.kq-c-status .kq-st')!.textContent).toBeTruthy()
    expect(row.querySelector('.kq-c-status .badge')).toBeNull()
    expect(row.className).toContain('stg-W_TRANSPORCIE')   // pasek 3px w kolorze etapu
    expect(row.querySelector('.kq-c-customs')!.textContent).toBe('—')
    fireEvent.click(screen.getByRole('button', { name: 'Etap' }))
    await waitFor(() => expect(document.querySelector('.kq-c-status')).toBeNull())
    expect(screen.queryByRole('columnheader', { name: /^Status/ })).toBeNull()
  })

  it('grupa zwija się strzałką; Grupuj „Magazyn" przestawia grupy', async () => {
    mount()
    await ready()
    fireEvent.click(document.querySelectorAll('.kq-caret')[0])
    await waitFor(() => expect(screen.queryByText('MSDU0806613')).toBeNull())
    fireEvent.click(screen.getByRole('button', { name: 'Magazyn' }))
    await waitFor(() => expect([...document.querySelectorAll('.kq-gtitle')].map(e => e.textContent))
      .toEqual(['DLT', 'ACME']))
    expect(localStorage.getItem('queueGroupBy')).toBe('warehouse')
  })

  it('klik w nagłówek kolumny sortuje wiersze w grupie', async () => {
    mount()
    await ready()
    fireEvent.click(screen.getByRole('columnheader', { name: /Nr kontenera/ }))
    await waitFor(() => expect(rowNos().slice(0, 3)).toEqual(['HLXU7654324', 'MSDU0806613', 'TCLU1234568']))
    fireEvent.click(screen.getByRole('columnheader', { name: /Nr kontenera/ }))
    await waitFor(() => expect(rowNos().slice(0, 3)).toEqual(['TCLU1234568', 'MSDU0806613', 'HLXU7654324']))
  })
})
