// @vitest-environment jsdom
// Kolejka Enterprise (plaster 5): zakładki szuflady Dokumenty / Wiadomości / Koszty na
// istniejących endpointach + zapisane widoki jako zakładki (zapis, przełączenie, usunięcie).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const CONTAINERS = [{
  id: 1, container_no: 'MSDU0806613', company_id: 1, company_name: 'Acme', supplier_name: 'Dostawca A',
  vessel: 'MV DEMO ATLAS', eta: '2026-08-01', atd: null, notify_date: '2026-08-10', transport_type: 'kolej',
  status: 'W_TRANSPORCIE', customs_status: 'BRAK', document_status: 'BRAK', purchasing_status: 'BRAK',
  order_numbers: '', delivery_note: '', incoming_delivery_no: '', purchase_note: '', forwarder_name: 'SPEDALFA',
  document_flow: '', sent_required: null, sent_number: '', sent_status: '', is_delayed: true,
  transport_id: null, order_number: null, warehouse_name: 'DLT', updated_at: '2026-08-01T10:00:00',
}]
const FILES = [
  { id: 5, container_id: 1, filename: 'BL_MSDU.pdf', content_type: 'application/pdf', size: 250_000,
    uploaded_by_login: 'jan', document_type_id: null, document_type_name: null,
    created_at: '2026-08-02T08:00:00' },
  { id: 6, container_id: 1, filename: 'packing.xlsx', content_type: '', size: 2048,
    uploaded_by_login: 'ola', document_type_id: null, document_type_name: null,
    created_at: '2026-08-03T08:00:00' },
]
const MESSAGES = [
  { id: 1, container_id: 1, body: 'Kiedy rozładunek?', user_login: 'jan', user_full_name: 'Jan K.',
    user_role: 'logistics', created_at: '2026-08-02T09:00:00' },
  { id: 2, container_id: 1, body: 'Jutro rano', user_login: 'admin', user_full_name: 'Admin',
    user_role: 'admin', created_at: '2026-08-02T09:05:00' },
]
const FREIGHT = [
  { id: 1, bl_number: 'BL1', invoice_number: '', forwarder_name: 'SPEDALFA', amount: 1000, currency: 'USD',
    amount_per_container: 500, containers: [{ id: 1 }, { id: 2 }], status: 'NOWA' },
  { id: 2, bl_number: 'BL2', invoice_number: '', forwarder_name: null, amount: 300, currency: 'USD',
    amount_per_container: 300, containers: [{ id: 1 }], status: 'NOWA' },
]
const calls = { get: [] as string[], post: [] as { path: string; body: unknown }[], upload: [] as string[] }
let freightForbidden = false

vi.mock('./api', () => ({
  api: {
    put: () => Promise.resolve({}),  // setPref → zapis profilu widoku (prefs.ts)
    get: (path: string) => {
      calls.get.push(path)
      if (path.startsWith('/api/containers?')) return Promise.resolve(CONTAINERS)
      if (path.endsWith('/attachments')) return Promise.resolve(FILES)
      if (path.endsWith('/messages')) return Promise.resolve(MESSAGES)
      if (path.startsWith('/api/freight-invoices')) {
        return freightForbidden ? Promise.reject(new Error('403')) : Promise.resolve(FREIGHT)
      }
      return Promise.resolve(path.startsWith('/api/containers/counts') ? {} : [])
    },
    post: (path: string, body: unknown) => { calls.post.push({ path, body }); return Promise.resolve({}) },
    upload: (path: string) => { calls.upload.push(path); return Promise.resolve({}) },
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

let search = ''
function Loc() { search = useLocation().search; return null }

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); freightForbidden = false; USER.role = 'admin'
  calls.get.length = 0; calls.post.length = 0; calls.upload.length = 0
})
afterEach(cleanup)

const mount = (url = '/kolejka?spolka=acme&kontener=1') => render(
  <MemoryRouter initialEntries={[url]}><QueuePage /><Loc /></MemoryRouter>)
// pełny render kolejki + 3 żądania szuflady — przy obciążonym runnerze domyślne 1 s bywa za mało
const openTab = async (name: RegExp) =>
  fireEvent.click(await screen.findByRole('tab', { name }))

describe('szuflada — zakładki Dokumenty / Wiadomości / Koszty', () => {
  it('Dokumenty: kafelki z rozszerzeniem, meta; nowe pliki tylko przez poczekalnię', async () => {
    mount()
    await openTab(/Dokumenty\s*2/)
    const items = document.querySelectorAll('.kq-docs li')
    expect(items.length).toBe(2)
    expect(items[0].querySelector('.kq-doc-ico.pdf')!.textContent).toBe('PDF')
    expect(items[0].textContent).toContain('244 kB')
    expect(items[0].textContent).toContain('jan')
    expect(items[1].querySelector('.kq-doc-ico')!.className).not.toContain('pdf')
    expect(document.querySelector('.kq-drop')).toBeNull()   // spec 2026-10-06: bez osobnego wgrywania
  })

  it('magazyn nie widzi strefy wgrywania', async () => {
    USER.role = 'warehouse'
    mount()
    await openTab(/Dokumenty/)
    await waitFor(() => expect(document.querySelectorAll('.kq-docs li').length).toBe(2))
    expect(document.querySelector('.kq-drop')).toBeNull()
  })

  it('Wiadomości: moje po prawej, wysyłka przez POST /messages', async () => {
    mount()
    await openTab(/Wiadomości\s*2/)
    const msgs = document.querySelectorAll('.kq-msg')
    expect(msgs[0].className).not.toContain('mine')
    expect(msgs[1].className).toContain('mine')
    expect(msgs[0].textContent).toContain('Jan K.')
    fireEvent.change(screen.getByRole('textbox', { name: /Napisz wiadomość/ }), { target: { value: 'OK' } })
    fireEvent.click(screen.getByRole('button', { name: 'Wyślij' }))
    await waitFor(() => expect(calls.post).toEqual([{ path: '/api/containers/1/messages', body: { body: 'OK' } }]))
  })

  it('Koszty: pozycje (udział w fakturze BL) i Razem per waluta; bez uprawnień zakładki nie ma', async () => {
    mount()
    await openTab(/Koszty/)
    expect(calls.get).toContain('/api/freight-invoices?container_id=1')
    // pozycje dochodzą asynchronicznie — przy pełnym przebiegu suite'u bywały jeszcze puste
    await waitFor(() => expect(document.querySelectorAll('.kq-costs > div').length).toBeGreaterThan(2))
    const rows = [...document.querySelectorAll('.kq-costs > div')].map(r => r.textContent)
    expect(rows[0]).toContain('BL1')
    expect(rows[0]).toContain('udział 1/2')
    expect(rows[0]).toContain('500,00 USD')
    expect(rows[2]).toMatch(/Razem.*800,00\sUSD/)
    cleanup()
    freightForbidden = true
    mount()
    await screen.findByRole('tab', { name: /Historia/ })
    await waitFor(() => expect(screen.queryByRole('tab', { name: /Koszty/ })).toBeNull())
  })
})

describe('zapisane widoki', () => {
  it('„+ Zapisz widok" zapisuje stan jako zakładkę; klik przywraca, ✕ usuwa', async () => {
    mount('/kolejka?spolka=acme&widok=late')
    await screen.findByText('MSDU0806613')
    vi.spyOn(window, 'prompt').mockReturnValue('Moje opóźnione')
    fireEvent.click(screen.getByRole('button', { name: '+ Zapisz widok' }))
    const tab = await screen.findByRole('button', { name: 'Moje opóźnione' })
    expect(tab.getAttribute('aria-pressed')).toBe('true')
    expect(JSON.parse(localStorage.getItem('queueViews')!)[0]).toMatchObject(
      { name: 'Moje opóźnione', search: '?spolka=acme&widok=late', groupBy: 'weekday' })
    // przełącz na inną zakładkę i wróć zapisanym widokiem
    fireEvent.click(screen.getByRole('button', { name: /^Wszystkie/ }))
    await waitFor(() => expect(search).not.toContain('widok=late'))
    fireEvent.click(screen.getByRole('button', { name: 'Moje opóźnione' }))
    await waitFor(() => expect(search).toContain('widok=late'))
    fireEvent.click(screen.getByRole('button', { name: 'Usuń widok: Moje opóźnione' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Moje opóźnione' })).toBeNull())
    expect(JSON.parse(localStorage.getItem('queueViews')!)).toEqual([])
  })
})
